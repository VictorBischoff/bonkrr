"""Spider for extracting media from Bunkr.site."""
import json
import signal
import sys
import os
from pathlib import Path
from typing import Generator, List, Optional, Dict, Any, Set, Union, Callable, TypeVar, Iterator
from urllib.parse import urljoin, urlparse
import random
import atexit
import re

from scrapy import Spider, Request
from scrapy.http import Response
from twisted.internet import reactor
from scrapy.exceptions import CloseSpider, DontCloseSpider
from twisted.internet.error import ReactorNotRunning
from scrapy.utils.project import get_project_settings

from ...core.config import DownloadConfig
from ...core.logger import setup_logger
from ...ui.progress import ProgressTracker
from ...downloader.rate_limiter import RateLimiter
from ...core.exceptions import ScrapyError, BunkrrError, SpiderError
from ...core.error_handler import ErrorHandler

from bs4 import BeautifulSoup, SoupStrainer

logger = setup_logger('bunkrr.scrapy.spiders')

# Type variables for callbacks
T = TypeVar('T')
CallbackType = Callable[[Response], Union[Generator[Request, None, None], Optional[Dict[str, Any]], None]]

# Compile regex patterns once
URL_PATTERN = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
ALBUM_ID_PATTERN = re.compile(r'/a/([a-zA-Z0-9]+)')
MEDIA_ID_PATTERN = re.compile(r'/v/([a-zA-Z0-9]+)')

# Create strainers once
ALBUM_STRAINER = SoupStrainer(['meta', 'h1', 'div'], attrs={
    'property': 'og:title',
    'class_': ['truncate', 'theItem']
})

MEDIA_STRAINER = SoupStrainer(['img', 'p', 'span'], attrs={
    'class_': ['grid-images_box-img', 'theSize', 'theDate']
})

class ResultPool:
    """Pool for reusing result objects."""
    
    def __init__(self, max_size: int = 1000):
        """Initialize result pool."""
        self._items: List[Dict] = []
        self._max_size = max_size
    
    def get(self) -> Dict:
        """Get an item from the pool."""
        if self._items:
            return self._items.pop()
        return {}
    
    def put(self, item: Dict) -> None:
        """Return an item to the pool."""
        if len(self._items) < self._max_size:
            item.clear()
            self._items.append(item)

class BunkrSpider(Spider):
    """Spider for extracting media from Bunkr.site."""
    
    name = 'bunkr'
    allowed_domains = [
        'bunkr.site', 'bunkr.ru', 'bunkr.ph', 'bunkr.is', 'bunkr.to', 'bunkr.fi',
        'i-kebab.bunkr.ru', 'i-pizza.bunkr.ru', 'i-burger.bunkr.ru',
        'kebab.bunkr.ru', 'pizza.bunkr.ru', 'burger.bunkr.ru',
        'c.bunkr-cache.se', 'get.bunkrr.su'
    ]
    
    # Modern browser user agents
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
    ]
    
    custom_settings = {
        # Concurrency settings
        'CONCURRENT_REQUESTS': 8,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
        'DOWNLOAD_TIMEOUT': 30,
        
        # Retry settings
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
        
        # Cache settings
        'HTTPCACHE_ENABLED': False,
        
        # Middleware settings
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy.downloadermiddlewares.retry.RetryMiddleware': 500,
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
            'scrapy.downloadermiddlewares.stats.DownloaderStats': 850,
            'scrapy.downloadermiddlewares.httpcache.HttpCacheMiddleware': None,
            'bunkrr.scrapy.middlewares.CustomRateLimiterMiddleware': 450,
        },
        
        # Request settings
        'COOKIES_ENABLED': False,
        'DOWNLOAD_DELAY': 1,
        
        # Log settings
        'LOG_LEVEL': 'DEBUG',
        
        # Reactor settings
        'TWISTED_REACTOR': 'twisted.internet.selectreactor.SelectReactor',
        
        # Stats settings
        'STATS_CLASS': 'scrapy.statscollectors.MemoryStatsCollector'
    }
    
    def __init__(
        self,
        config: DownloadConfig,
        start_urls: List[str],
        parent_folder: Path,
        progress_tracker: Optional[ProgressTracker] = None,
        **kwargs
    ):
        """Initialize spider with configuration."""
        super().__init__(**kwargs)
        self.config = config
        self.start_urls = start_urls
        self.parent_folder = parent_folder
        self.progress_tracker = progress_tracker
        
        # Initialize counters and state
        self.media_count = 0
        self.failed_count = 0
        self.processed_urls: Set[str] = set()
        self.running = True
        self._shutdown_requested = False
        self._cleanup_registered = False
        
        # Verify download directory
        try:
            self.parent_folder.mkdir(parents=True, exist_ok=True)
            if not self.parent_folder.is_dir():
                raise CloseSpider(f"Download path is not a directory: {self.parent_folder}")
            if not os.access(self.parent_folder, os.W_OK):
                raise CloseSpider(f"No write permission for download path: {self.parent_folder}")
        except Exception as e:
            raise CloseSpider(f"Failed to setup download directory: {str(e)}")
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            requests_per_window=self.config.rate_limit,
            window_seconds=self.config.rate_window
        )
        
        # Set up signal handlers and cleanup
        self._setup_handlers()
        
        logger.info(
            "Initialized BunkrSpider with parent_folder: %s, start_urls: %s",
            parent_folder,
            start_urls
        )
        
        self._visited_urls: Set[str] = set()
        self._result_pool = ResultPool()
    
    def _setup_handlers(self):
        """Set up signal handlers and cleanup."""
        if not self._cleanup_registered:
            # Register signal handlers
            signal.signal(signal.SIGINT, self._handle_sigint)
            signal.signal(signal.SIGTERM, self._handle_sigint)
            
            # Register cleanup handler
            atexit.register(self._cleanup)
            
            self._cleanup_registered = True
    
    def _shutdown(self, reason: str = 'shutdown', force: bool = False) -> None:
        """Handle spider shutdown."""
        if not self.running and not force:
            return
            
        self.running = False
        logger.info(
            "Spider shutting down (%s). Stats - Processed: %d, Failed: %d",
            reason,
            self.media_count,
            self.failed_count
        )
        
        try:
            # Stop the reactor if it's running
            if reactor.running:
                try:
                    reactor.callFromThread(reactor.stop)
                except ReactorNotRunning:
                    pass
                except Exception as e:
                    logger.error("Error stopping reactor: %s", str(e))
            
            # Close progress tracker if exists
            if self.progress_tracker:
                self.progress_tracker.close()
            
            # Clean up rate limiter
            if hasattr(self, 'rate_limiter'):
                self.rate_limiter.close()
            
        except Exception as e:
            logger.error("Error during shutdown: %s", str(e))
            if force:
                sys.exit(1)

    def _handle_sigint(self, signum, frame):
        """Handle SIGINT (Ctrl+C) gracefully."""
        if self._shutdown_requested:
            logger.info("Forced shutdown requested.")
            self._shutdown(reason='forced_shutdown', force=True)
            return
            
        self._shutdown_requested = True
        self._shutdown(reason='interrupt')
    
    def _cleanup(self):
        """Clean up resources."""
        self._shutdown(reason='cleanup', force=True)
    
    def closed(self, reason):
        """Called when the spider is closed."""
        self._shutdown(reason=reason)
        
        # Don't exit here, let the cleanup handler handle it
        if reason == 'finished':
            raise DontCloseSpider("Spider finished but cleanup pending")
    
    def _create_request(
        self,
        url: str,
        callback: CallbackType,
        priority: int = 0,
        meta: Optional[Dict[str, Any]] = None
    ) -> Request:
        """Create a request with proper headers and settings."""
        headers = self.get_headers()
        if meta is None:
            meta = {}
        
        return Request(
            url=url,
            callback=callback,
            priority=priority,
            headers=headers,
            meta=meta,
            dont_filter=True,
            errback=self.handle_error
        )
    
    def get_headers(self):
        """Get request headers with random user agent."""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
        }
    
    def _get_media_selectors(self):
        """Get media selectors with fallbacks."""
        return {
            'album_title': [
                'h1.text-xl::text',
                'h1.truncate::text',
                'meta[property="og:title"]::attr(content)',
                'title::text'
            ],
            'media_links': [
                'div.theItem a[href^="/f/"]::attr(href)',
                'a.after\\:absolute[href^="/f/"]::attr(href)',
                'a[href^="/f/"]::attr(href)'
            ],
            'download_link': [
                'a[href^="https://get.bunkrr.su/file/"]::attr(href)',
                'a[href*="get.bunkrr.su"]::attr(href)',
                'a[href*="download"]::attr(href)'
            ],
            'image_src': [
                'figure.relative img.max-h-full::attr(src)',
                'img.max-h-full::attr(src)',
                'img.max-w-full::attr(src)',
                'meta[property="og:image"]::attr(content)'
            ],
            'video_src': [
                'video#player source::attr(src)',
                'video source::attr(src)',
                'meta[property="og:video"]::attr(content)'
            ],
            'file_size': [
                'p.text-xs::text',
                'span.text-xs::text',
                'div.text-xs::text'
            ]
        }
    
    def _try_selectors(self, response: Response, selector_type: str, get_all: bool = False) -> Optional[Union[str, List[str]]]:
        """Try multiple selectors and return first match or all matches."""
        selectors = self._get_media_selectors().get(selector_type, [])
        for selector in selectors:
            results = response.css(selector).getall() if get_all else response.css(selector).get()
            if results:
                if get_all:
                    return [r.strip() for r in results if r and r.strip()]
                return results.strip()
        return [] if get_all else None
    
    def _try_selectors_all(self, response: Response, selector_type: str) -> List[str]:
        """Try multiple selectors and return all matches."""
        return self._try_selectors(response, selector_type, get_all=True) or []
    
    def parse_album(self, response: Response) -> Generator[Request, None, None]:
        """Parse album page to extract media links."""
        if not self.running:
            return
            
        album_url = response.meta.get('album_url', response.url)
        logger.debug("Parsing album page: %s (Status: %d)", album_url, response.status)
        
        try:
            # Extract album title
            album_title = self._try_selectors(response, 'album_title')
            if not album_title:
                logger.warning("No album title found for URL: %s", album_url)
                album_title = album_url.split('/')[-1]
            
            album_title = album_title.strip()
            logger.debug("Found album title: %s", album_title)
            
            # Extract media links
            media_links = self._try_selectors_all(response, 'media_links')
            
            if not media_links:
                logger.warning("No media links found in album: %s", album_url)
                self._handle_media_failure(response)
                return
            
            logger.info(
                "Found %d media links in album: %s",
                len(media_links),
                album_title
            )
            
            # Process each media link
            for link in media_links:
                if not self.running or not link:
                    continue
                    
                media_url = urljoin(response.url, link)
                logger.debug("Processing media URL: %s", media_url)
                
                yield self._create_request(
                    url=media_url,
                    callback=self.parse_media,
                    meta={
                        'album_title': album_title,
                        'media_url': media_url
                    }
                )
                
        except Exception as e:
            logger.error(
                "Error parsing album page %s: %s",
                response.url,
                str(e),
                exc_info=True
            )
            self._handle_media_failure(response)
    
    def _extract_media_info(self, response: Response) -> Optional[Dict[str, Any]]:
        """Extract media information from response."""
        media_type = None
        media_src = None
        
        # Check for image content
        image_src = self._try_selectors(response, 'image_src')
        if image_src:
            media_type = 'image'
            media_src = image_src
            logger.debug("Found image source: %s", image_src)
        
        # Check for video content
        if not media_src:
            video_src = self._try_selectors(response, 'video_src')
            if video_src:
                media_type = 'video'
                media_src = video_src
                logger.debug("Found video source: %s", video_src)
        
        # Try meta tags as fallback
        if not media_src:
            media_src = response.css('meta[property="og:image"]::attr(content), meta[property="og:url"]::attr(content)').get()
            if media_src:
                media_type = 'image' if any(ext in media_src for ext in ['.gif', '.jpg', '.jpeg', '.png', '.webp']) else 'video'
                logger.debug("Found media source from meta tags: %s", media_src)
        
        return {'type': media_type, 'src': media_src} if media_src else None

    def _create_media_item(
        self,
        response: Response,
        download_link: str,
        media_info: Dict[str, Any],
        album_title: str
    ) -> Dict[str, Any]:
        """Create media item dictionary."""
        thumbnail = response.css('meta[property="og:image"]::attr(content)').get()
        file_size = self._try_selectors(response, 'file_size')
        
        return {
            'file_urls': [download_link],
            'media_type': media_info['type'],
            'media_src': media_info['src'],
            'thumbnail_url': thumbnail,
            'file_size': file_size.strip() if file_size else None,
            'album_title': album_title,
            'source_url': response.url,
            'filename': media_info['src'].split('/')[-1],
            'headers': self.get_headers()
        }

    def parse_media(self, response: Response) -> Optional[Dict[str, Any]]:
        """Parse media page to extract download URL."""
        if not self.running:
            return None
            
        album_title = response.meta.get('album_title', 'unknown')
        media_url = response.meta.get('media_url', response.url)
        logger.debug("Parsing media page: %s (Status: %d)", media_url, response.status)
        
        try:
            # Extract direct download link
            download_link = self._try_selectors(response, 'download_link')
            if not download_link:
                logger.warning("No download link found on page: %s", response.url)
                self._handle_media_failure(response)
                return None
            
            logger.debug("Found download link: %s", download_link)
            
            # Extract media information
            media_info = self._extract_media_info(response)
            if not media_info:
                logger.warning("No media source found on page: %s", response.url)
                self._handle_media_failure(response)
                return None
            
            # Create and return media item
            item = self._create_media_item(response, download_link, media_info, album_title)
            self._handle_media_success()
            return item
            
        except Exception as e:
            logger.error(
                "Error parsing media page %s: %s",
                response.url,
                str(e),
                exc_info=True
            )
            self._handle_media_failure(response)
            return None

    def _handle_media_success(self):
        """Handle successful media extraction."""
        self.media_count += 1
        if self.progress_tracker:
            self.progress_tracker.update(completed=1)

    def _handle_media_failure(self, response: Response):
        """Handle media extraction failure."""
        logger.debug("Response body: %s", response.text[:1000])
        if self.progress_tracker:
            self.progress_tracker.update(failed=1)
        self.failed_count += 1
    
    def handle_error(self, failure):
        """Handle request failures."""
        error = ScrapyError(
            message=str(failure.value),
            spider_name=self.name,
            url=failure.request.url,
            details=str(failure.getTracebackObject()) if failure.getTracebackObject() else None
        )
        
        ErrorHandler.handle_error(error, context="spider_request", reraise=False)
        
        self.failed_count += 1
        if self.progress_tracker:
            self.progress_tracker.update(failed=1)

    def normalize_url(self, url: str) -> str:
        """Normalize URL for comparison."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def start_requests(self) -> Generator[Request, None, None]:
        """Generate initial requests."""
        for url in self.config.start_urls:
            normalized = self.normalize_url(url)
            if normalized not in self._visited_urls:
                self._visited_urls.add(normalized)
                yield Request(url=url, callback=self.parse)
    
    def parse(self, response: Response) -> Optional[Dict[str, Any]]:
        """Parse response and delegate to appropriate parser."""
        if not self.running:
            return None
        
        try:
            # Extract album ID from URL
            album_match = ALBUM_ID_PATTERN.search(response.url)
            if album_match:
                return self._parse_album(response)
            
            # Extract media ID from URL
            media_match = MEDIA_ID_PATTERN.search(response.url)
            if media_match:
                return self._parse_media(response)
            
            logger.warning("URL %s doesn't match any known patterns", response.url)
            return None
            
        except Exception as e:
            logger.error("Error parsing %s: %s", response.url, str(e))
            self._handle_media_failure(response)
            return None
    
    def _parse_album(self, response: Response) -> Dict[str, Any]:
        """Parse album page."""
        soup = BeautifulSoup(response.text, 'lxml', parse_only=ALBUM_STRAINER)
        result = self._result_pool.get()
        
        try:
            # Extract meta title
            meta_title = soup.find('meta', property='og:title')
            if meta_title and meta_title.get('content'):
                result['title'] = meta_title['content']
            
            # Extract h1 title
            h1_title = soup.find('h1', class_='truncate')
            if h1_title:
                result['header'] = h1_title.get_text(strip=True)
            
            # Extract media items
            media_items = []
            for item in soup.find_all('div', class_='theItem'):
                media_item = self._result_pool.get()
                
                # Extract file info
                filename = item.find('p', style='display:none;')
                if filename:
                    media_item['filename'] = filename.get_text(strip=True)
                
                size = item.find('p', class_='theSize')
                if size:
                    media_item['size'] = size.get_text(strip=True)
                
                date = item.find('span', class_='theDate')
                if date:
                    media_item['date'] = date.get_text(strip=True)
                
                thumbnail = item.find('img', class_='grid-images_box-img')
                if thumbnail and thumbnail.get('src'):
                    media_item['thumbnail'] = thumbnail['src']
                
                media_items.append(media_item)
            
            result['media_items'] = media_items
            return result
            
        except Exception as e:
            self._result_pool.put(result)
            raise SpiderError(f"Failed to parse album: {e}")
    
    def _parse_media(self, response: Response) -> Dict[str, Any]:
        """Parse media page."""
        soup = BeautifulSoup(response.text, 'lxml', parse_only=MEDIA_STRAINER)
        result = self._result_pool.get()
        
        try:
            # Extract media info
            img = soup.find('img', class_='grid-images_box-img')
            if img and img.get('src'):
                result['url'] = img['src']
            
            size = soup.find('p', class_='theSize')
            if size:
                result['size'] = size.get_text(strip=True)
            
            date = soup.find('span', class_='theDate')
            if date:
                result['date'] = date.get_text(strip=True)
            
            return result
            
        except Exception as e:
            self._result_pool.put(result)
            raise SpiderError(f"Failed to parse media: {e}")
