"""Media processor module."""
import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, AsyncIterator
from urllib.parse import urlparse
from collections import deque

from twisted.internet import selectreactor
selectreactor.install()

from scrapy.crawler import CrawlerRunner, Crawler
from scrapy.utils.project import get_project_settings
from scrapy.utils.defer import deferred_to_future
from scrapy.spiders import Spider
from scrapy.http import Request, Response
from scrapy.statscollectors import StatsCollector

from ..core.config import DownloadConfig
from ..core.logger import setup_logger
from ..core.error_handler import ErrorHandler
from ..core.exceptions import ScrapyError
from ..ui.progress import ProgressTracker
from ..utils.storage import Cache, CacheConfig, MemoryCache

logger = setup_logger('bunkrr.scrapy')

@dataclass
class RequestStats:
    """Request statistics."""
    url: str
    status_code: int
    response_time: float
    request_size: int
    response_size: int

class RunningStats:
    """Efficient running statistics calculator."""
    
    def __init__(self):
        """Initialize running stats."""
        self._count = 0
        self._mean = 0.0
        self._min = float('inf')
        self._max = float('-inf')
        self._total = 0.0
    
    def add(self, value: float) -> None:
        """Add value to running stats."""
        self._count += 1
        delta = value - self._mean
        self._mean += delta / self._count
        self._min = min(self._min, value)
        self._max = max(self._max, value)
        self._total += value
    
    @property
    def count(self) -> int:
        """Get count of values."""
        return self._count
    
    @property
    def mean(self) -> float:
        """Get mean value."""
        return self._mean
    
    @property
    def min(self) -> float:
        """Get minimum value."""
        return float('-inf') if self._min == float('inf') else self._min
    
    @property
    def max(self) -> float:
        """Get maximum value."""
        return float('inf') if self._max == float('-inf') else self._max
    
    @property
    def total(self) -> float:
        """Get total of values."""
        return self._total

class StatsManager:
    """Manages request statistics and caching with optimized data structures."""
    
    def __init__(self, ttl: int = 300, max_stats: int = 1000):
        """Initialize stats manager."""
        self.cache = MemoryCache('responses', ttl=ttl)
        self._stats: deque[RequestStats] = deque(maxlen=max_stats)
        self._response_times = RunningStats()
        self._request_sizes = RunningStats()
        self._response_sizes = RunningStats()
        self._success_count = 0
        self._failed_count = 0
    
    def add_request(self, stats: RequestStats) -> None:
        """Add request statistics."""
        self._stats.append(stats)
        
        # Update running stats
        self._response_times.add(stats.response_time)
        self._request_sizes.add(stats.request_size)
        self._response_sizes.add(stats.response_size)
        
        # Update status counts
        if 200 <= stats.status_code < 300:
            self._success_count += 1
        elif stats.status_code >= 400:
            self._failed_count += 1
    
    def cache_response(self, url: str, response: Response) -> None:
        """Cache response."""
        self.cache.set(url, response)
    
    def get_cached_response(self, url: str) -> Optional[Response]:
        """Get cached response."""
        return self.cache.get(url)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics."""
        if not self._stats:
            return {}
        
        return {
            'requests': {
                'total': len(self._stats),
                'success': self._success_count,
                'failed': self._failed_count
            },
            'timing': {
                'avg': self._response_times.mean,
                'min': self._response_times.min,
                'max': self._response_times.max
            },
            'sizes': {
                'request': {
                    'avg': self._request_sizes.mean,
                    'total': self._request_sizes.total
                },
                'response': {
                    'avg': self._response_sizes.mean,
                    'total': self._response_sizes.total
                }
            },
            'cache': {
                'size': self.cache.get_size(),
                'items': len(self.cache)
            }
        }

class EnhancedStatsCollector(StatsCollector):
    """Enhanced stats collector with performance metrics."""
    
    def __init__(self, crawler: Crawler):
        """Initialize stats collector."""
        super().__init__(crawler)
        self.stats_manager = crawler.spider.stats_manager
    
    def response_downloaded(self, response: Response, request: Request, spider: Spider) -> None:
        """Record response metrics."""
        start_time = request.meta.get('download_start_time', 0)
        response_time = time.time() - start_time if start_time else 0
        
        stats = RequestStats(
            response_time=response_time,
            request_size=len(request.body) if request.body else 0,
            response_size=len(response.body) if response.body else 0,
            status_code=response.status,
            url=request.url
        )
        
        self.stats_manager.add_request(stats)
        if 200 <= response.status < 300:
            self.stats_manager.cache_response(request.url, response)

class MediaProcessor:
    """Media processor with enhanced error handling and stats collection."""
    
    def __init__(self, config: DownloadConfig):
        """Initialize media processor."""
        self.config = config
        self.progress = ProgressTracker()
        self.stats_manager = StatsManager()
        
        # Configure settings
        settings = get_project_settings()
        settings.update(config.scrapy.to_dict())
        settings.update({
            'STATS_CLASS': 'bunkrr.scrapy.processor.EnhancedStatsCollector',
            'DUPEFILTER_CLASS': None,
            'HTTPCACHE_ENABLED': False
        })
        
        self.runner = CrawlerRunner(settings)
        logger.debug("MediaProcessor initialized with config: %s", config)
    
    @ErrorHandler.wrap_async
    async def _handle_spider_error(self, failure: Any, spider: Spider, url: str) -> None:
        """Handle spider errors with context."""
        error_info = {
            'url': url,
            'spider': spider.name,
            'error': str(failure.value),
            'traceback': failure.getTraceback().decode()
        }
        
        logger.error(
            "Spider error for %s: %s",
            url,
            error_info['error'],
            extra=error_info
        )
        
        raise ScrapyError(
            message=f"Failed to process URL: {url}",
            spider=spider.name,
            url=url,
            details=str(failure.value)
        )
    
    @asynccontextmanager
    async def _manage_crawler(self, url: str) -> AsyncIterator[Crawler]:
        """Manage crawler lifecycle."""
        crawler = None
        try:
            crawler = self.runner.create_crawler('bunkr')
            crawler.spider.stats_manager = self.stats_manager
            yield crawler
        finally:
            if crawler and crawler.engine.running:
                await deferred_to_future(crawler.engine.stop())
    
    @ErrorHandler.wrap_async
    async def process_urls(self, urls: List[str]) -> None:
        """Process URLs with progress tracking."""
        total = len(urls)
        self.progress.start(total)
        
        try:
            for url in urls:
                domain = urlparse(url).netloc
                logger.info("Processing URL: %s", url)
                
                async with self._manage_crawler(url) as crawler:
                    deferred = crawler.crawl(url=url, domain=domain)
                    await deferred_to_future(deferred)
                
                self.progress.increment()
        finally:
            self.progress.finish()
    
    async def __aenter__(self) -> 'MediaProcessor':
        """Enter async context."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        if self.runner.crawlers:
            await deferred_to_future(self.runner.stop())
