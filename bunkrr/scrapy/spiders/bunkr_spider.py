"""Spider for extracting media from Bunkr.site."""
import json
import signal
import sys
import os
from pathlib import Path
from typing import Generator, List, Optional, Dict, Any, Set
from urllib.parse import urljoin
import random
import atexit

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
from ...core.exceptions import ScrapyError

logger = setup_logger('bunkrr.scrapy.spiders')

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
    
    def _setup_handlers(self):
        """Set up signal handlers and cleanup."""
        if not self._cleanup_registered:
            # Register signal handlers
            signal.signal(signal.SIGINT, self._handle_sigint)
            signal.signal(signal.SIGTERM, self._handle_sigint)
            
            # Register cleanup handler
            atexit.register(self._cleanup)
            
            self._cleanup_registered = True
    
    def _cleanup(self):
        """Clean up resources."""
        if not self.running:
            return
            
        self.running = False
        logger.info("Cleaning up resources...")
        
        try:
            # Stop the reactor if it's running
            if reactor.running:
                try:
                    reactor.callFromThread(reactor.stop)
                except ReactorNotRunning:
                    pass
                except Exception as e:
                    logger.error("Error stopping reactor: %s", str(e))
        except Exception as e:
            logger.error("Error during cleanup: %s", str(e))
    
    def _handle_sigint(self, signum, frame):
        """Handle SIGINT (Ctrl+C) gracefully."""
        if self._shutdown_requested:  # If already shutting down, force cleanup
            logger.info("Forced shutdown requested. Cleaning up...")
            self._cleanup()
            return
            
        self._shutdown_requested = True
        self.running = False
        logger.info("\nReceived interrupt signal. Shutting down gracefully...")
        logger.info("Processed %d URLs successfully, %d failed", self.media_count, self.failed_count)
        
        try:
            # Close spider gracefully
            if hasattr(self, 'crawler') and self.crawler:
                self.crawler.engine.close_spider(self, 'shutdown_requested')
            
            # Cleanup will be handled by atexit handler
            
        except Exception as e:
            logger.error("Error during shutdown: %s", str(e))
            self._cleanup()
    
    def closed(self, reason):
        """Called when the spider is closed."""
        logger.info("Spider closed: %s", reason)
        logger.info("Final stats - Processed: %d, Failed: %d", self.media_count, self.failed_count)
        
        if not self.running:
            self._cleanup()
            
        # Don't exit here, let the cleanup handler handle it
        if reason == 'finished':
            raise DontCloseSpider("Spider finished but cleanup pending")
    
    def start_requests(self) -> Generator[Request, None, None]:
        """Generate initial requests from start URLs."""
        if not self.start_urls:
            logger.warning("No start URLs provided")
            return
            
        for url in self.start_urls:
            if not self.running:
                break
                
            if url in self.processed_urls:
                logger.debug("Skipping already processed URL: %s", url)
                continue
                
            self.processed_urls.add(url)
            logger.info("Starting request for album URL: %s", url)
            
            yield Request(
                url=url,
                callback=self.parse_album,
                errback=self.handle_error,
                headers=self.get_headers(),
                meta={
                    'album_url': url,
                    'dont_redirect': True,
                    'handle_httpstatus_list': list(range(400, 600)),
                    'dont_retry': False,
                    'download_timeout': 30,
                    'max_retry_times': 3
                },
                dont_filter=True,
                priority=1  # Higher priority for album pages
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
    
    def _try_selectors(self, response: Response, selector_type: str) -> Optional[str]:
        """Try multiple selectors and return first match."""
        selectors = self._get_media_selectors().get(selector_type, [])
        for selector in selectors:
            result = response.css(selector).get()
            if result:
                return result.strip()
        return None
    
    def _try_selectors_all(self, response: Response, selector_type: str) -> List[str]:
        """Try multiple selectors and return all matches."""
        selectors = self._get_media_selectors().get(selector_type, [])
        for selector in selectors:
            results = response.css(selector).getall()
            if results:
                return [r.strip() for r in results if r and r.strip()]
        return []
    
    def parse_album(self, response: Response) -> Generator[Request, None, None]:
        """Parse album page to extract media links."""
        if not self.running:
            return
            
        album_url = response.meta.get('album_url', response.url)
        logger.debug("Parsing album page: %s (Status: %d)", album_url, response.status)
        
        try:
            # Log response headers for debugging
            logger.debug("Response headers: %s", response.headers)
            
            # Try different selectors for album title
            album_title = self._try_selectors(response, 'album_title')
            if not album_title:
                logger.warning("No album title found for URL: %s", album_url)
                album_title = album_url.split('/')[-1]
            
            album_title = album_title.strip()
            logger.debug("Found album title: %s", album_title)
            
            # Extract media links using multiple selectors
            media_links = self._try_selectors_all(response, 'media_links')
            
            if not media_links:
                logger.warning("No media links found in album: %s", album_url)
                logger.debug("Response body: %s", response.text[:1000])
                if self.progress_tracker:
                    self.progress_tracker.update(failed=1)
                self.failed_count += 1
                return
            
            logger.info(
                "Found %d media links in album: %s",
                len(media_links),
                album_title
            )
            logger.debug("Media links found: %s", media_links)
            
            # Process each media link
            for link in media_links:
                if not self.running:
                    break
                    
                if not link:
                    continue
                    
                media_url = urljoin(response.url, link)
                logger.debug("Processing media URL: %s", media_url)
                
                yield Request(
                    url=media_url,
                    callback=self.parse_media,
                    errback=self.handle_error,
                    headers=self.get_headers(),
                    meta={
                        'album_title': album_title,
                        'media_url': media_url,
                        'dont_redirect': True,
                        'handle_httpstatus_list': list(range(400, 600)),
                        'dont_retry': False,
                        'download_timeout': 30,
                        'max_retry_times': 3
                    },
                    dont_filter=True,
                    priority=0  # Normal priority for media pages
                )
                
        except Exception as e:
            logger.error(
                "Error parsing album page %s: %s",
                response.url,
                str(e),
                exc_info=True
            )
            if self.progress_tracker:
                self.progress_tracker.update(failed=1)
            self.failed_count += 1
    
    def parse_media(self, response: Response) -> Optional[Dict[str, Any]]:
        """Parse media page to extract download URL."""
        if not self.running:
            return None
            
        album_title = response.meta.get('album_title', 'unknown')
        media_url = response.meta.get('media_url', response.url)
        logger.debug("Parsing media page: %s (Status: %d)", media_url, response.status)
        
        try:
            # Log response headers for debugging
            logger.debug("Response headers: %s", response.headers)
            
            # Extract direct download link
            download_link = self._try_selectors(response, 'download_link')
            if not download_link:
                logger.warning("No download link found on page: %s", response.url)
                logger.debug("Response body: %s", response.text[:1000])
                if self.progress_tracker:
                    self.progress_tracker.update(failed=1)
                self.failed_count += 1
                return None
            
            logger.debug("Found download link: %s", download_link)
            
            # Extract media type and source
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
            
            if not media_src:
                # Try meta tags
                media_src = response.css('meta[property="og:image"]::attr(content), meta[property="og:url"]::attr(content)').get()
                if media_src:
                    media_type = 'image' if '.gif' in media_src or any(ext in media_src for ext in ['.jpg', '.jpeg', '.png', '.webp']) else 'video'
                    logger.debug("Found media source from meta tags: %s", media_src)
            
            if not media_src:
                logger.warning("No media source found on page: %s", response.url)
                logger.debug("Response body: %s", response.text[:1000])
                if self.progress_tracker:
                    self.progress_tracker.update(failed=1)
                self.failed_count += 1
                return None
            
            # Get file size if available
            file_size = self._try_selectors(response, 'file_size')
            if file_size:
                file_size = file_size.strip()
                logger.debug("File size: %s", file_size)
            
            # Get thumbnail if available
            thumbnail = response.css('meta[property="og:image"]::attr(content)').get()
            
            # Return item for pipeline processing
            item = {
                'file_urls': [download_link],  # Use the direct download link
                'media_type': media_type,
                'media_src': media_src,  # Original media source
                'thumbnail_url': thumbnail,
                'file_size': file_size,
                'album_title': album_title,
                'source_url': response.url,
                'filename': media_src.split('/')[-1],
                'headers': self.get_headers()  # Use same headers for file download
            }
            
            self.media_count += 1
            if self.progress_tracker:
                self.progress_tracker.update(completed=1)
            
            return item
            
        except Exception as e:
            logger.error(
                "Error parsing media page %s: %s",
                response.url,
                str(e),
                exc_info=True
            )
            if self.progress_tracker:
                self.progress_tracker.update(failed=1)
            self.failed_count += 1
            return None
    
    def handle_error(self, failure):
        """Handle request failures."""
        logger.error(
            "Request failed for URL %s: %s",
            failure.request.url,
            str(failure.value),
            exc_info=failure.getTracebackObject()
        )
        
        # Log additional error details
        if hasattr(failure.value, 'response'):
            response = failure.value.response
            logger.debug("Error response status: %d", response.status)
            logger.debug("Error response headers: %s", response.headers)
        
        self.failed_count += 1
        if self.progress_tracker:
            self.progress_tracker.update(failed=1)
