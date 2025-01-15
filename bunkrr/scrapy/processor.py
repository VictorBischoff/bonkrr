"""Media processor module."""
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any, Set
from urllib.parse import urlparse

from twisted.internet import selectreactor, reactor
selectreactor.install()

from scrapy.crawler import CrawlerRunner, Crawler
from scrapy.utils.project import get_project_settings
from scrapy.utils.log import configure_logging
from scrapy.utils.defer import deferred_to_future
from scrapy.spiders import Spider
from scrapy.http import Request, Response
from scrapy.statscollectors import StatsCollector
from scrapy.exceptions import NotConfigured

from ..core.config import DownloadConfig
from ..core.logger import setup_logger
from ..core.error_handler import handle_async_errors
from ..core.exceptions import ScrapyError, ShutdownError
from ..ui.progress import ProgressTracker
from ..utils.caching import Cache, MemoryCache

logger = setup_logger('bunkrr.processor')

class ResponseCache:
    """Cache for Scrapy responses."""
    
    def __init__(self, ttl: int = 300, max_size: Optional[int] = None):
        """Initialize response cache."""
        self.cache = MemoryCache('responses', ttl=ttl, max_size=max_size)
        self.hits = 0
        self.misses = 0
        
    def _get_cache_key(self, url: str, headers: Optional[Dict] = None) -> str:
        """Generate cache key for URL and headers."""
        if not headers:
            return url
        return f"{url}:{hash(frozenset(headers.items()))}"
        
    def get(self, url: str, headers: Optional[Dict] = None) -> Optional[Response]:
        """Get response from cache."""
        key = self._get_cache_key(url, headers)
        response = self.cache.get(key)
        
        if response is not None:
            self.hits += 1
            return response
            
        self.misses += 1
        return None
        
    def set(self, url: str, response: Response, headers: Optional[Dict] = None) -> None:
        """Cache response."""
        key = self._get_cache_key(url, headers)
        self.cache.set(key, response)
        
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            'hits': self.hits,
            'misses': self.misses,
            'total': total,
            'hit_rate': hit_rate,
            'size': self.cache.get_size()
        }

class RequestDeduplicator:
    """Request deduplication with fingerprinting."""
    
    def __init__(self, ttl: int = 3600):
        """Initialize request deduplicator."""
        self.seen: Dict[str, float] = {}
        self.ttl = ttl
        
    def _clean_expired(self) -> None:
        """Clean expired entries."""
        now = time.time()
        expired = [
            k for k, v in self.seen.items()
            if now - v > self.ttl
        ]
        for key in expired:
            del self.seen[key]
            
    def _get_fingerprint(self, request: Request) -> str:
        """Generate request fingerprint."""
        components = [
            request.method,
            request.url,
            str(sorted(request.headers.items())),
            str(request.body)
        ]
        return ':'.join(components)
        
    def is_duplicate(self, request: Request) -> bool:
        """Check if request is duplicate."""
        self._clean_expired()
        
        fingerprint = self._get_fingerprint(request)
        is_duplicate = fingerprint in self.seen
        
        if not is_duplicate:
            self.seen[fingerprint] = time.time()
            
        return is_duplicate

class EnhancedStatsCollector(StatsCollector):
    """Enhanced stats collector with performance metrics."""
    
    def __init__(self, crawler):
        """Initialize stats collector."""
        super().__init__(crawler)
        self.response_times: List[float] = []
        self.request_sizes: List[int] = []
        self.response_sizes: List[int] = []
        
    def response_downloaded(self, response: Response, request: Request, spider: Spider) -> None:
        """Record response metrics."""
        # Response time
        start_time = request.meta.get('download_start_time', 0)
        if start_time:
            response_time = time.time() - start_time
            self.response_times.append(response_time)
            self.max_value('response_time_max', response_time)
            self.min_value('response_time_min', response_time)
            
        # Size metrics
        request_size = len(request.body) if request.body else 0
        response_size = len(response.body) if response.body else 0
        
        self.request_sizes.append(request_size)
        self.response_sizes.append(response_size)
        
        self.max_value('request_size_max', request_size)
        self.max_value('response_size_max', response_size)
        
    def get_stats(self) -> Dict[str, Any]:
        """Get enhanced statistics."""
        stats = super().get_stats()
        
        # Add response time stats
        if self.response_times:
            avg_time = sum(self.response_times) / len(self.response_times)
            stats['response_time_avg'] = avg_time
            
        # Add size stats
        if self.request_sizes:
            avg_req_size = sum(self.request_sizes) / len(self.request_sizes)
            stats['request_size_avg'] = avg_req_size
            
        if self.response_sizes:
            avg_resp_size = sum(self.response_sizes) / len(self.response_sizes)
            stats['response_size_avg'] = avg_resp_size
            
        return stats

class MediaProcessor:
    """Media processor class with performance optimizations."""
    
    def __init__(self, config: DownloadConfig):
        """Initialize the media processor."""
        self.config = config
        self.progress_tracker = ProgressTracker()
        self._active_crawlers: Dict[str, Crawler] = {}
        self._cleanup_tasks: List[asyncio.Task] = []
        
        # Performance optimizations
        self.response_cache = ResponseCache(
            ttl=300,  # 5 minutes
            max_size=50 * 1024 * 1024  # 50MB
        )
        self.deduplicator = RequestDeduplicator()
        
        # Configure Scrapy settings
        settings = get_project_settings()
        settings.update(self.config.scrapy.to_dict())
        
        # Add custom components
        settings.update({
            'STATS_CLASS': 'bunkrr.scrapy.processor.EnhancedStatsCollector',
            'DUPEFILTER_CLASS': None,  # Use our own deduplication
            'HTTPCACHE_ENABLED': False  # Use our own caching
        })
        
        self.runner = CrawlerRunner(settings)
        logger.debug("MediaProcessor initialized with config: %s", config)
        
    def _get_domain(self, url: str) -> str:
        """Get domain from URL."""
        return urlparse(url).netloc
        
    async def _handle_spider_error(
        self,
        failure: Any,
        spider: Spider,
        url: str
    ) -> None:
        """Handle spider errors with detailed context."""
        error_info = {
            'url': url,
            'spider_name': spider.name,
            'error_type': failure.__class__.__name__,
            'error_msg': str(failure.value),
            'traceback': failure.getTraceback().decode()
        }
        
        logger.error(
            "Spider error for %s: %s",
            url,
            error_info['error_msg'],
            extra={'error_info': error_info}
        )
        
        raise ScrapyError(
            f"Failed to process URL: {url}",
            spider_name=spider.name,
            url=url,
            details=str(failure.value)
        )
        
    async def _cleanup_crawler(self, crawler: Crawler) -> None:
        """Clean up a crawler instance."""
        try:
            if crawler.engine.running:
                await deferred_to_future(crawler.engine.stop())
            self._active_crawlers.pop(crawler.spider.name, None)
            logger.debug("Cleaned up crawler for spider: %s", crawler.spider.name)
        except Exception as e:
            logger.error(
                "Error cleaning up crawler %s: %s",
                crawler.spider.name,
                str(e)
            )
            
    @asynccontextmanager
    async def _manage_crawler(self, url: str) -> Crawler:
        """Manage crawler lifecycle with proper cleanup."""
        crawler = None
        try:
            crawler = self.runner.create_crawler('bunkr')
            self._active_crawlers[crawler.spider.name] = crawler
            yield crawler
        finally:
            if crawler:
                cleanup_task = asyncio.create_task(
                    self._cleanup_crawler(crawler)
                )
                self._cleanup_tasks.append(cleanup_task)
                cleanup_task.add_done_callback(self._cleanup_tasks.remove)
                
    async def process_urls(self, urls: List[str]) -> None:
        """Process URLs with performance optimizations."""
        # Group URLs by domain for better connection reuse
        domain_groups: Dict[str, List[str]] = {}
        for url in urls:
            domain = self._get_domain(url)
            domain_groups.setdefault(domain, []).append(url)
            
        # Process each domain group
        for domain, domain_urls in domain_groups.items():
            logger.info("Processing %d URLs for domain %s", len(domain_urls), domain)
            
            async with self._manage_crawler(domain_urls[0]) as crawler:
                # Configure spider
                spider = crawler.spiders.create('bunkr')
                spider.start_urls = domain_urls
                
                # Add performance hooks
                spider.response_cache = self.response_cache
                spider.deduplicator = self.deduplicator
                
                # Start crawling
                try:
                    await deferred_to_future(crawler.crawl())
                except Exception as e:
                    logger.error("Crawler error for domain %s: %s", domain, e)
                    raise ScrapyError(f"Crawler error: {e}")
                    
                # Log performance stats
                stats = crawler.stats.get_stats()
                cache_stats = self.response_cache.get_stats()
                
                logger.info(
                    "Domain %s processed: %s requests, %s responses, "
                    "cache hit rate: %.2f%%",
                    domain,
                    stats.get('downloader/request_count', 0),
                    stats.get('downloader/response_count', 0),
                    cache_stats['hit_rate'] * 100
                )

    async def __aenter__(self) -> 'MediaProcessor':
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit with cleanup."""
        try:
            # Clean up any remaining crawlers
            crawlers = list(self._active_crawlers.values())
            if crawlers:
                logger.debug("Cleaning up %d remaining crawlers", len(crawlers))
                await asyncio.gather(
                    *(self._cleanup_crawler(c) for c in crawlers),
                    return_exceptions=True
                )
            
            # Wait for any pending cleanup tasks
            if self._cleanup_tasks:
                await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error("Error during MediaProcessor cleanup: %s", str(e))
            raise ShutdownError("Failed to clean up MediaProcessor") from e
