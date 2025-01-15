"""Spider implementation for extracting media content from Bunkr.site."""
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import (
    Any, Callable, Counter as CounterType, Deque, Dict, Generator,
    Iterator, List, Optional, Set, TypeVar, Union
)
from urllib.parse import urljoin, urlparse
import atexit
import json
import os
import random
import re
import signal
import sys
import time
import traceback
import uuid

from bs4 import BeautifulSoup, SoupStrainer
from scrapy import Spider, Request
from scrapy.exceptions import CloseSpider, DontCloseSpider, IgnoreRequest
from scrapy.http import Response
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor
from twisted.internet.error import ReactorNotRunning

from ...core.config import DownloadConfig
from ...core.error_handler import ErrorHandler, ErrorStats, ErrorContext
from ...core.exceptions import (
    BunkrrError, ParsingError, RateLimitError, ScrapyError, SpiderError,
    HTTPError
)
from ...core.logger import setup_logger
from ...downloader.rate_limiter import RateLimiter
from ...ui.progress import ProgressTracker
from ...utils.backoff import ExponentialBackoff

logger = setup_logger('bunkrr.scrapy.spiders')

# Type aliases
T = TypeVar('T')
ResponseCallback = Callable[
    [Response],
    Union[Generator[Request, None, None], Optional[Dict[str, Any]], None]
]

class _ResultPool:
    """Internal pool for reusing result dictionaries to reduce memory allocations."""
    
    def __init__(self, max_size: int = 1000) -> None:
        """Initialize the result pool.
        
        Args:
            max_size: Maximum number of items to keep in the pool
        """
        self._items: List[Dict[str, Any]] = []
        self._max_size = max_size
    
    def get(self) -> Dict[str, Any]:
        """Get a result dictionary from the pool or create a new one."""
        return self._items.pop() if self._items else {}
    
    def put(self, item: Dict[str, Any]) -> None:
        """Return a result dictionary to the pool if not full."""
        if len(self._items) < self._max_size:
            item.clear()
            self._items.append(item)

class BunkrSpider(Spider):
    """Spider for extracting media content from Bunkr.site."""
    
    name = 'bunkr'
    
    # Supported domains for media extraction
    allowed_domains = [
        # Main domains
        'bunkr.site', 'bunkr.ru', 'bunkr.ph', 'bunkr.is', 'bunkr.to', 'bunkr.fi',
        # CDN domains
        'i-kebab.bunkr.ru', 'i-pizza.bunkr.ru', 'i-burger.bunkr.ru',
        'kebab.bunkr.ru', 'pizza.bunkr.ru', 'burger.bunkr.ru',
        'c.bunkr-cache.se', 'get.bunkrr.su'
    ]
    
    # Spider configuration
    custom_settings = {
        'CONCURRENT_REQUESTS': 8,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
        'DOWNLOAD_TIMEOUT': 30,
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        'HTTPCACHE_ENABLED': False,
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy.downloadermiddlewares.retry.RetryMiddleware': 500,
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
            'scrapy.downloadermiddlewares.stats.DownloaderStats': 850,
            'scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware': None,
            'bunkrr.scrapy.middlewares.RateLimitMiddleware': 450,
        },
        'COOKIES_ENABLED': False,
        'DOWNLOAD_DELAY': 1,
        'LOG_LEVEL': 'DEBUG',
        'TWISTED_REACTOR': 'twisted.internet.selectreactor.SelectReactor',
        'STATS_CLASS': 'scrapy.statscollectors.MemoryStatsCollector'
    }
    
    # Private constants
    _URL_PATTERN = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
    _ALBUM_ID_PATTERN = re.compile(r'/a/([a-zA-Z0-9]+)')
    _MEDIA_ID_PATTERN = re.compile(r'/v/([a-zA-Z0-9]+)')
    
    _ALBUM_STRAINER = SoupStrainer(['meta', 'h1', 'div'], attrs={
        'property': 'og:title',
        'class_': ['truncate', 'theItem']
    })
    
    _MEDIA_STRAINER = SoupStrainer(['img', 'p', 'span'], attrs={
        'class_': ['grid-images_box-img', 'theSize', 'theDate']
    })
    
    _USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
    ]
    
    def __init__(self, *args, **kwargs):
        """Initialize spider with error tracking and retry logic."""
        super().__init__(*args, **kwargs)
        
        # Error tracking
        self._error_stats = ErrorStats(window_size=3600)  # 1 hour window
        self._error_context = ErrorContext()
        
        # Retry handling
        self._backoff = ExponentialBackoff(
            initial=1.0,
            maximum=60.0,
            factor=2.0,
            jitter=True
        )
        
        # Circuit breaker
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._error_threshold = 5
        self._error_window = timedelta(minutes=5)
        self._last_errors: Dict[str, Deque[datetime]] = defaultdict(lambda: deque(maxlen=10))
        
        # Request tracking
        self._request_times: Dict[str, float] = {}
        self._request_contexts: Dict[str, Dict[str, Any]] = {}
        
        # Result pool
        self._result_pool = _ResultPool()
        
        logger.debug("BunkrSpider initialized with error tracking and retry logic")
    
    def _should_retry(self, url: str, error: Exception) -> bool:
        """Determine if request should be retried based on error history.
        
        Args:
            url: Request URL
            error: Exception that occurred
            
        Returns:
            bool: Whether to retry the request
        """
        error_type = error.__class__.__name__
        now = datetime.now()
        
        # Update error tracking
        self._last_errors[url].append(now)
        self._error_counts[url] += 1
        
        # Check circuit breaker
        recent_errors = sum(
            1 for t in self._last_errors[url]
            if now - t <= self._error_window
        )
        
        if recent_errors >= self._error_threshold:
            logger.warning(
                "Circuit breaker triggered for %s: %d errors in %s",
                url, recent_errors, self._error_window
            )
            return False
        
        # Check error type
        if isinstance(error, (RateLimitError, ParsingError)):
            return True
            
        if isinstance(error, HTTPError):
            return error.status_code in self.custom_settings['RETRY_HTTP_CODES']
        
        return False
    
    def _track_request(self, request: Request) -> None:
        """Track request timing and context.
        
        Args:
            request: Scrapy Request object
        """
        self._request_times[request.url] = time.time()
        self._request_contexts[request.url] = {
            'method': request.method,
            'headers': dict(request.headers),
            'meta': dict(request.meta)
        }
    
    def _handle_error(
        self,
        error: Exception,
        url: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Handle request error with enhanced context and tracking.
        
        Args:
            error: Exception that occurred
            url: Request URL
            context: Optional additional context
        """
        # Calculate duration if request was tracked
        duration = None
        if url in self._request_times:
            duration = time.time() - self._request_times[url]
            del self._request_times[url]
        
        # Build error context
        error_context = {
            'url': url,
            'spider': self.name,
            'duration': duration,
            'timestamp': datetime.now().isoformat()
        }
        
        # Add request context if available
        if url in self._request_contexts:
            error_context.update(self._request_contexts[url])
            del self._request_contexts[url]
        
        # Add custom context
        if context:
            error_context.update(context)
        
        # Track error
        self._error_stats.add_error(
            error_type=error.__class__.__name__,
            duration=duration,
            context=error_context
        )
        
        # Log error with context
        logger.error(
            "Request error for %s: %s",
            url,
            str(error),
            extra={'error_context': error_context},
            exc_info=True
        )
    
    @ErrorHandler.wrap
    def start_requests(self) -> Generator[Request, None, None]:
        """Start requests with error handling."""
        try:
            for url in self.start_urls:
                yield self._create_request(url)
        except Exception as e:
            self._handle_error(e, 'start_urls')
            raise
    
    def _create_request(
        self,
        url: str,
        callback: Optional[ResponseCallback] = None,
        **kwargs: Any
    ) -> Request:
        """Create request with error tracking.
        
        Args:
            url: Target URL
            callback: Optional callback function
            **kwargs: Additional request parameters
            
        Returns:
            Request: Configured request object
        """
        request = Request(
            url=url,
            callback=callback or self.parse,
            headers={'User-Agent': random.choice(self._USER_AGENTS)},
            dont_filter=kwargs.pop('dont_filter', False),
            **kwargs
        )
        
        self._track_request(request)
        return request
    
    @ErrorHandler.wrap
    def parse(self, response: Response) -> Generator[Request, None, None]:
        """Parse response with error handling.
        
        Args:
            response: Scrapy Response object
            
        Yields:
            Request objects for further processing
        """
        try:
            # Extract URLs from response
            urls = self._extract_urls(response)
            
            # Process each URL
            for url in urls:
                try:
                    if self._ALBUM_ID_PATTERN.search(url):
                        yield self._create_request(url, callback=self.parse_album)
                    elif self._MEDIA_ID_PATTERN.search(url):
                        yield self._create_request(url, callback=self.parse_media)
                except Exception as e:
                    self._handle_error(e, url, {'source': 'parse_url'})
                    
        except Exception as e:
            self._handle_error(e, response.url, {'source': 'parse'})
            raise
    
    @ErrorHandler.wrap
    def parse_album(self, response: Response) -> Generator[Request, None, None]:
        """Parse album page with error handling.
        
        Args:
            response: Scrapy Response object
            
        Yields:
            Request objects for media items
        """
        try:
            # Parse album metadata
            soup = BeautifulSoup(response.text, 'lxml', parse_only=self._ALBUM_STRAINER)
            
            # Extract media URLs
            media_urls = self._extract_media_urls(soup)
            
            # Process each media URL
            for url in media_urls:
                try:
                    yield self._create_request(url, callback=self.parse_media)
                except Exception as e:
                    self._handle_error(e, url, {
                        'source': 'parse_album',
                        'album_url': response.url
                    })
                    
        except Exception as e:
            self._handle_error(e, response.url, {'source': 'parse_album'})
            raise
    
    @ErrorHandler.wrap
    def parse_media(self, response: Response) -> Optional[Dict[str, Any]]:
        """Parse media page with error handling.
        
        Args:
            response: Scrapy Response object
            
        Returns:
            Optional[Dict[str, Any]]: Media metadata if successful
        """
        try:
            # Parse media metadata
            soup = BeautifulSoup(response.text, 'lxml', parse_only=self._MEDIA_STRAINER)
            
            # Extract media information
            media_info = self._extract_media_info(soup)
            
            if not media_info:
                raise ParsingError(
                    "Failed to extract media information",
                    data_type='media_info',
                    source=response.url
                )
            
            return media_info
            
        except Exception as e:
            self._handle_error(e, response.url, {'source': 'parse_media'})
            raise
    
    def _extract_urls(self, response: Response) -> List[str]:
        """Extract URLs from response with error handling.
        
        Args:
            response: Scrapy Response object
            
        Returns:
            List[str]: List of extracted URLs
        """
        try:
            urls = []
            for match in self._URL_PATTERN.finditer(response.text):
                url = match.group()
                if not url.startswith('http'):
                    url = urljoin(response.url, url)
                urls.append(url)
            return urls
            
        except Exception as e:
            self._handle_error(e, response.url, {'source': 'extract_urls'})
            return []
    
    def _extract_media_urls(self, soup: BeautifulSoup) -> List[str]:
        """Extract media URLs from soup with error handling.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            List[str]: List of media URLs
        """
        try:
            urls = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                if self._MEDIA_ID_PATTERN.search(href):
                    urls.append(href)
            return urls
            
        except Exception as e:
            self._handle_error(e, 'unknown', {'source': 'extract_media_urls'})
            return []
    
    def _extract_media_info(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Extract media information from soup with error handling.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Optional[Dict[str, Any]]: Media information if successful
        """
        try:
            result = self._result_pool.get()
            
            # Extract media details
            img = soup.find('img', class_='grid-images_box-img')
            if img and img.get('src'):
                result['url'] = img['src']
                result['type'] = 'image'
                
            size_elem = soup.find('p', class_='theSize')
            if size_elem:
                result['size'] = size_elem.text.strip()
                
            date_elem = soup.find('span', class_='theDate')
            if date_elem:
                result['date'] = date_elem.text.strip()
            
            return result if result else None
            
        except Exception as e:
            self._handle_error(e, 'unknown', {'source': 'extract_media_info'})
            return None
        finally:
            if result:
                self._result_pool.put(result)
    
    def process_request(self, request: Request, spider: Spider) -> Optional[Request]:
        """Process request with error handling.
        
        Args:
            request: Request being processed
            spider: Spider instance
            
        Returns:
            Optional[Request]: Modified request or None
        """
        try:
            # Track request
            self._track_request(request)
            
            # Add error context
            request.meta['error_context'] = {
                'spider': self.name,
                'start_time': time.time(),
                'request_id': str(uuid.uuid4())
            }
            
            return request
            
        except Exception as e:
            self._handle_error(e, request.url, {'source': 'process_request'})
            return None
    
    def process_response(
        self,
        request: Request,
        response: Response,
        spider: Spider
    ) -> Union[Response, Request]:
        """Process response with error handling.
        
        Args:
            request: Original request
            response: Response being processed
            spider: Spider instance
            
        Returns:
            Union[Response, Request]: Processed response or retry request
        """
        try:
            # Check response status
            if response.status >= 400:
                error = HTTPError(
                    f"HTTP {response.status}",
                    method=request.method,
                    url=request.url,
                    status_code=response.status
                )
                
                if self._should_retry(request.url, error):
                    # Calculate backoff delay
                    delay = self._backoff.get_delay(request.url)
                    request.meta['retry_delay'] = delay
                    
                    logger.info(
                        "Retrying %s in %.2f seconds (attempt %d)",
                        request.url,
                        delay,
                        self._error_counts[request.url]
                    )
                    
                    return request
                else:
                    self._handle_error(error, request.url)
            
            return response
            
        except Exception as e:
            self._handle_error(e, request.url, {'source': 'process_response'})
            return response
    
    def process_exception(
        self,
        request: Request,
        exception: Exception,
        spider: Spider
    ) -> Optional[Union[Response, Request]]:
        """Process exception with error handling.
        
        Args:
            request: Failed request
            exception: Exception that occurred
            spider: Spider instance
            
        Returns:
            Optional[Union[Response, Request]]: Retry request or None
        """
        try:
            if self._should_retry(request.url, exception):
                # Calculate backoff delay
                delay = self._backoff.get_delay(request.url)
                request.meta['retry_delay'] = delay
                
                logger.info(
                    "Retrying %s in %.2f seconds (attempt %d)",
                    request.url,
                    delay,
                    self._error_counts[request.url]
                )
                
                return request
            else:
                self._handle_error(exception, request.url)
                return None
                
        except Exception as e:
            self._handle_error(e, request.url, {'source': 'process_exception'})
            return None
    
    def closed(self, reason: str) -> None:
        """Handle spider closure with error cleanup.
        
        Args:
            reason: Reason for closure
        """
        try:
            # Log error statistics
            logger.info(
                "Spider closed (%s) - Error stats: %s",
                reason,
                json.dumps(self._error_stats.get_stats(), indent=2)
            )
            
            # Clear error tracking
            self._error_counts.clear()
            self._last_errors.clear()
            self._request_times.clear()
            self._request_contexts.clear()
            
        except Exception as e:
            logger.error("Error during spider cleanup: %s", str(e), exc_info=True)
