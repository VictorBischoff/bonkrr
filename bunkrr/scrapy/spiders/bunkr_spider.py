"""Spider for extracting media from Bunkr.site."""
import json
from pathlib import Path
from typing import Any, Dict, Generator, Optional, List
from urllib.parse import urljoin

from scrapy import Spider
from scrapy.http import Request, Response

from ...core.config import DownloadConfig
from ...core.logger import setup_logger
from ...ui.progress import ProgressTracker

logger = setup_logger('bunkrr.scrapy.spiders.bunkr')

class BunkrSpider(Spider):
    """Spider for extracting media from Bunkr.site."""
    
    name = 'bunkr'
    allowed_domains = ['bunkr.site', 'cdn.bunkr.site']
    
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
        
        # Initialize counters
        self.media_count = 0
        self.failed_count = 0
        
        logger.info(
            "Initialized BunkrSpider with parent_folder: %s, start_urls: %s",
            parent_folder,
            start_urls
        )
        
    def start_requests(self) -> Generator[Request, None, None]:
        """Generate initial requests from start URLs."""
        for url in self.start_urls:
            logger.info("Starting request for URL: %s", url)
            yield Request(
                url,
                callback=self.parse_album,
                errback=self.handle_error,
                meta={'dont_redirect': True},
                dont_filter=True
            )
            
    def parse_album(self, response: Response) -> Generator[Dict[str, Any], None, None]:
        """Extract media URLs from album page."""
        try:
            # Extract album title
            album_title = response.css('h1.text-xl::text').get()
            if not album_title:
                album_title = response.url.split('/')[-1]
            logger.info("Processing album: %s", album_title)
            
            # Extract media items
            media_items = response.css('div.grid div.relative')
            if not media_items:
                logger.warning("No media items found in album: %s", response.url)
                self.failed_count += 1
                return
                
            total_files = len(media_items)
            logger.info("Found %d media items in album", total_files)
            
            # Process each media item
            for item in media_items:
                try:
                    # Extract media URL
                    media_url = item.css('a::attr(href)').get()
                    if not media_url:
                        logger.warning("No media URL found in item")
                        self.failed_count += 1
                        continue
                        
                    # Build full URL if needed
                    if not media_url.startswith(('http://', 'https://')):
                        media_url = urljoin(response.url, media_url)
                        
                    # Extract filename from URL or use default
                    filename = media_url.split('/')[-1]
                    
                    # Create media item
                    media_item = {
                        'album_title': album_title,
                        'url': media_url,
                        'file_urls': [media_url],
                        'filename': filename,
                        'total_files': total_files,
                        'parent_folder': str(self.parent_folder)
                    }
                    
                    self.media_count += 1
                    logger.debug("Yielding media item: %s", media_item)
                    yield media_item
                    
                except Exception as e:
                    logger.error(
                        "Error processing media item in album %s: %s",
                        response.url,
                        str(e),
                        exc_info=True
                    )
                    self.failed_count += 1
                    
        except Exception as e:
            logger.error(
                "Error parsing album %s: %s",
                response.url,
                str(e),
                exc_info=True
            )
            self.failed_count += 1
            
    def handle_error(self, failure):
        """Handle request failures."""
        logger.error(
            "Request failed for URL %s: %s",
            failure.request.url,
            str(failure.value),
            exc_info=failure.getTracebackObject()
        )
        self.failed_count += 1
