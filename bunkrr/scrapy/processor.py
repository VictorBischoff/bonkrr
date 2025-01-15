"""Media processor module."""
import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, AsyncIterator
from urllib.parse import urlparse
from collections import deque
import json
import traceback

from twisted.internet import selectreactor
selectreactor.install()

from scrapy.crawler import CrawlerRunner, Crawler
from scrapy.utils.project import get_project_settings
from scrapy.utils.defer import deferred_to_future
from scrapy.spiders import Spider
from scrapy.http import Request, Response
from scrapy.statscollectors import StatsCollector
from scrapy.utils.log import failure_to_exc_info

from ..core.config import DownloadConfig
from ..core.logger import setup_logger, log_exception
from ..core.error_handler import ErrorHandler
from ..core.exceptions import ScrapyError, BunkrrError
from ..ui.progress import ProgressTracker
from ..utils.storage import Cache, CacheConfig, MemoryCache
from ..core.error_handler import handle_async_errors

# Set up processor logger with debug level and structured output
logger = setup_logger(
    'bunkrr.scrapy',
    level='DEBUG',
    log_dir='logs',
    console=True,
    file=True,
    json=True,
    scrapy_integration=True
)

@dataclass
class RequestStats:
    """Request statistics."""
    url: str
    status_code: int
    response_time: float
    request_size: int
    response_size: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            'url': self.url,
            'status_code': self.status_code,
            'response_time': self.response_time,
            'request_size': self.request_size,
            'response_size': self.response_size
        }

class RunningStats:
    """Efficient running statistics calculator."""
    
    def __init__(self):
        """Initialize running stats."""
        self._count = 0
        self._mean = 0.0
        self._min = float('inf')
        self._max = float('-inf')
        self._total = 0.0
        self._start_time = time.time()
    
    def add(self, value: float) -> None:
        """Add value to running stats."""
        self._count += 1
        delta = value - self._mean
        self._mean += delta / self._count
        self._min = min(self._min, value)
        self._max = max(self._max, value)
        self._total += value
        
        # Log significant changes
        if value > self._max * 1.5:  # Significant spike
            logger.warning(
                "Performance spike detected",
                extra={
                    'value': value,
                    'mean': self._mean,
                    'max': self._max,
                    'delta_percent': ((value - self._mean) / self._mean) * 100
                }
            )
    
    def get_stats(self) -> Dict[str, float]:
        """Get current statistics."""
        return {
            'count': self._count,
            'mean': self._mean,
            'min': float('-inf') if self._min == float('inf') else self._min,
            'max': float('inf') if self._max == float('-inf') else self._max,
            'total': self._total,
            'duration': time.time() - self._start_time
        }

class StatsManager:
    """Manages request statistics and caching with optimized data structures."""
    
    def __init__(self, ttl: int = 300, max_stats: int = 1000):
        """Initialize stats manager."""
        config = CacheConfig(
            name='responses',
            ttl=ttl,
            max_size=max_stats,
            compress=True
        )
        self.cache = MemoryCache(config)
        self._stats: deque[RequestStats] = deque(maxlen=max_stats)
        self._response_times = RunningStats()
        self._request_sizes = RunningStats()
        self._response_sizes = RunningStats()
        self._success_count = 0
        self._failed_count = 0
        self._start_time = time.time()
        
        logger.debug(
            "StatsManager initialized",
            extra={
                'config': {
                    'ttl': ttl,
                    'max_stats': max_stats,
                    'cache_config': config.__dict__
                }
            }
        )
    
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
            logger.warning(
                "Request failed",
                extra={
                    'stats': stats.to_dict(),
                    'success_rate': (
                        self._success_count /
                        (self._success_count + self._failed_count)
                    )
                }
            )
    
    def cache_response(self, url: str, response: Response) -> None:
        """Cache response."""
        try:
            self.cache.set(url, response)
            logger.debug(
                "Response cached",
                extra={
                    'url': url,
                    'size': len(response.body),
                    'cache_size': len(self.cache)
                }
            )
        except Exception as e:
            log_exception(
                logger,
                e,
                "Failed to cache response",
                url=url,
                response_size=len(response.body)
            )
    
    def get_cached_response(self, url: str) -> Optional[Response]:
        """Get cached response."""
        try:
            response = self.cache.get(url)
            if response:
                logger.debug(
                    "Cache hit",
                    extra={
                        'url': url,
                        'size': len(response.body)
                    }
                )
            return response
        except Exception as e:
            log_exception(
                logger,
                e,
                "Failed to retrieve cached response",
                url=url
            )
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics."""
        if not self._stats:
            return {}
        
        duration = time.time() - self._start_time
        stats = {
            'requests': {
                'total': len(self._stats),
                'success': self._success_count,
                'failed': self._failed_count,
                'success_rate': (
                    self._success_count /
                    (self._success_count + self._failed_count)
                )
            },
            'timing': self._response_times.get_stats(),
            'sizes': {
                'request': self._request_sizes.get_stats(),
                'response': self._response_sizes.get_stats()
            },
            'cache': {
                'size': self.cache.get_size(),
                'items': len(self.cache)
            },
            'duration': duration,
            'requests_per_second': len(self._stats) / duration
        }
        
        logger.debug(
            "Stats snapshot",
            extra={'stats': stats}
        )
        
        return stats

class EnhancedStatsCollector(StatsCollector):
    """Enhanced stats collector with performance metrics."""
    
    def __init__(self, crawler: Crawler):
        """Initialize stats collector."""
        super().__init__(crawler)
        self.stats_manager = crawler.spider.stats_manager
        logger.debug(
            "EnhancedStatsCollector initialized",
            extra={'spider': crawler.spider.name}
        )
    
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
            
        logger.debug(
            "Response metrics recorded",
            extra={
                'stats': stats.to_dict(),
                'spider': spider.name
            }
        )

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
            'HTTPCACHE_ENABLED': False,
            'LOG_ENABLED': True,
            'LOG_FILE': 'logs/scrapy.log',
            'LOG_LEVEL': 'DEBUG',
            'LOG_FORMAT': '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            'LOG_DATEFORMAT': '%Y-%m-%d %H:%M:%S',
            'TWISTED_REACTOR': 'twisted.internet.asyncio.AsyncioSelectorReactor',
            'DOWNLOAD_HANDLERS': {
                'file': 'scrapy.core.downloader.handlers.file.FileDownloadHandler',
                'http': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
                'https': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
            }
        })
        
        self.runner = CrawlerRunner(settings)
        logger.info(
            "MediaProcessor initialized",
            extra={
                'config': config.to_dict(),
                'settings': dict(settings)
            }
        )
    
    @ErrorHandler.wrap_async
    async def _handle_spider_error(self, failure: Any, spider: Spider, url: str) -> None:
        """Handle spider errors with context."""
        error_info = {
            'url': url,
            'spider': spider.name,
            'error': str(failure.value),
            'traceback': failure.getTraceback().decode(),
            'stats': spider.crawler.stats.get_stats()
        }
        
        log_exception(
            logger,
            failure.value,
            "Spider error",
            spider=spider,
            url=url,
            stats=error_info['stats']
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
        start_time = time.time()
        crawler = None
        try:
            crawler = self.runner.create_crawler('bunkr')
            crawler.spider.stats_manager = self.stats_manager
            logger.debug(
                "Created crawler",
                extra={
                    'url': url,
                    'spider': crawler.spider.name,
                    'settings': crawler.settings.copy_to_dict()
                }
            )
            yield crawler
        finally:
            if crawler:
                duration = time.time() - start_time
                if crawler.engine.running:
                    logger.debug(
                        "Stopping crawler",
                        extra={
                            'url': url,
                            'spider': crawler.spider.name,
                            'duration': duration,
                            'stats': crawler.stats.get_stats()
                        }
                    )
                    await deferred_to_future(crawler.engine.stop())
                else:
                    logger.debug(
                        "Crawler not running",
                        extra={
                            'url': url,
                            'spider': crawler.spider.name,
                            'duration': duration
                        }
                    )
    
    @ErrorHandler.wrap_async(
        target_error=BunkrrError,
        context={'processor': 'MediaProcessor', 'method': 'process_urls'}
    )
    async def process_urls(self, urls: List[str], download_path: Optional[str] = None) -> tuple[int, int]:
        """Process URLs with progress tracking.
        
        Args:
            urls: List of URLs to process
            download_path: Optional path to download directory
            
        Returns:
            Tuple of (success_count, failed_count)
        """
        total = len(urls)
        self.progress.start(total)
        success_count = failed_count = 0
        start_time = time.time()
        
        logger.info(
            "Starting URL processing",
            extra={
                'total_urls': total,
                'download_path': download_path,
                'state': 'start'
            }
        )
        
        try:
            for url in urls:
                url_start_time = time.time()
                domain = urlparse(url).netloc
                logger.info(
                    "Processing URL",
                    extra={
                        'url': url,
                        'domain': domain,
                        'state': 'processing'
                    }
                )
                
                try:
                    async with self._manage_crawler(url) as crawler:
                        if download_path:
                            crawler.spider.download_path = download_path
                            logger.debug(
                                "Set download path",
                                extra={
                                    'url': url,
                                    'path': download_path
                                }
                            )
                        
                        logger.debug(
                            "Starting crawl",
                            extra={
                                'url': url,
                                'spider': crawler.spider.name
                            }
                        )
                        deferred = crawler.crawl(url=url, domain=domain)
                        await deferred_to_future(deferred)
                        
                        url_duration = time.time() - url_start_time
                        stats = crawler.stats.get_stats()
                        logger.info(
                            "URL processed successfully",
                            extra={
                                'url': url,
                                'duration': url_duration,
                                'stats': stats,
                                'state': 'success'
                            }
                        )
                        success_count += 1
                        
                except Exception as e:
                    url_duration = time.time() - url_start_time
                    log_exception(
                        logger,
                        e,
                        "Failed to process URL",
                        url=url,
                        duration=url_duration,
                        domain=domain
                    )
                    failed_count += 1
                
                self.progress.increment()
                logger.debug(
                    "Progress update",
                    extra={
                        'success': success_count,
                        'failed': failed_count,
                        'remaining': total - (success_count + failed_count)
                    }
                )
                
        finally:
            duration = time.time() - start_time
            self.progress.finish()
            logger.info(
                "URL processing complete",
                extra={
                    'total': total,
                    'success': success_count,
                    'failed': failed_count,
                    'duration': duration,
                    'success_rate': success_count / total if total > 0 else 0,
                    'state': 'complete'
                }
            )
            
        return success_count, failed_count
    
    async def __aenter__(self) -> 'MediaProcessor':
        """Enter async context."""
        logger.debug("Entering MediaProcessor context")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        if self.runner.crawlers:
            logger.debug(
                "Exiting MediaProcessor context",
                extra={
                    'crawlers': len(self.runner.crawlers),
                    'stats': self.stats_manager.get_stats()
                }
            )
            await deferred_to_future(self.runner.stop())
        else:
            logger.debug(
                "Exiting MediaProcessor context",
                extra={'crawlers': 0}
            )
