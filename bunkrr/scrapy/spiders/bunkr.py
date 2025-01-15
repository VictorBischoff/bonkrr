"""Spider for extracting media from Bunkr.site."""
import json
from pathlib import Path
from typing import Any, Dict, Generator, Optional, List
from urllib.parse import urljoin

from scrapy.http import Request, Response
from scrapy.spiders import Spider

from ...core.config import DownloadConfig
from ...core.logger import setup_logger
from ...core.exceptions import ScrapyError
from ...ui.progress import ProgressTracker

logger = setup_logger('bunkrr.spider')

class BunkrSpider(Spider):
    """Spider for extracting media from Bunkr.site."""
    
    name = 'bunkr'
    allowed_domains = ['bunkr.site', 'bunkr.ru', 'bunkr.ph', 'bunkr.is', 'bunkr.to', 'bunkr.fi']
    
    def __init__(
        self,
        config: Optional[DownloadConfig] = None,
        start_urls: Optional[List[str]] = None,
        parent_folder: Optional[Path] = None,
        progress_tracker: Optional[ProgressTracker] = None,
        *args,
        **kwargs
    ):
        """Initialize spider with configuration."""
        super().__init__(*args, **kwargs)
        self.config = config or DownloadConfig()
        self.parent_folder = parent_folder or self.config.downloads_path
        self.start_urls = start_urls or []
        self.media_count = 0
        self.failed_count = 0
        self.progress = progress_tracker or ProgressTracker()
        
        logger.info(
            "Initialized BunkrSpider with settings: %s",
            json.dumps({
                'parent_folder': str(self.parent_folder),
                'start_urls': self.start_urls
            }, indent=2)
        )
    
    def start_requests(self) -> Generator[Request, None, None]:
        """Generate initial requests from start URLs."""
        logger.debug("Starting requests for URLs: %s", self.start_urls)
        for url in self.start_urls:
            logger.info("Creating request for album URL: %s", url)
            yield Request(
                url=url,
                callback=self.parse_album,
                errback=self.handle_error,
                dont_filter=True,
                meta={
                    'album_url': url,
                    'dont_redirect': True,
                    'handle_httpstatus_list': list(range(400, 600))  # Handle all error codes
                }
            )
    
    def parse_album(self, response: Response) -> Generator[Dict[str, Any], None, None]:
        """Parse album page and extract media URLs."""
        logger.debug("Parsing album page: %s", response.url)
        
        try:
            # Extract album title
            album_title = response.css('h1.text-xl::text').get()
            if not album_title:
                album_title = response.css('title::text').get() or 'Unknown Album'
            album_title = album_title.strip()
            
            # Extract media items
            media_items = response.css('div[data-media-index]')
            total_files = len(media_items)
            
            if total_files == 0:
                logger.warning("No media items found in album: %s", response.url)
                self.failed_count += 1
                return
                
            logger.info(
                "Found %d media items in album: %s",
                total_files,
                album_title
            )
            
            # Update progress tracking
            self.progress.update_album(album_title, total_files)
            
            # Process each media item
            for item in media_items:
                try:
                    # Extract media URL and filename
                    media_url = item.css('a::attr(href)').get()
                    if not media_url:
                        logger.warning("No media URL found for item in album: %s", album_title)
                        self.failed_count += 1
                        self.progress.update_progress(advance=1, failed=True)
                        continue
                        
                    media_url = urljoin(response.url, media_url)
                    filename = item.css('a::text').get() or media_url.split('/')[-1]
                    
                    # Create media item for pipeline
                    media_item = {
                        'album_title': album_title,
                        'url': media_url,
                        'filename': filename,
                        'file_urls': [media_url],
                        'parent_folder': self.parent_folder,
                        'total_files': total_files
                    }
                    
                    logger.debug(
                        "Created media item: %s",
                        json.dumps(media_item, default=str)
                    )
                    
                    self.media_count += 1
                    yield media_item
                    
                except Exception as e:
                    logger.error(
                        "Error processing media item in album %s: %s",
                        album_title,
                        str(e),
                        exc_info=True
                    )
                    self.failed_count += 1
                    self.progress.update_progress(advance=1, failed=True)
                    continue
                    
        except Exception as e:
            logger.error(
                "Error parsing album %s: %s",
                response.url,
                str(e),
                exc_info=True
            )
            self.failed_count += 1
            raise ScrapyError(f"Failed to parse album: {response.url}", str(e))
    
    def handle_error(self, failure):
        """Handle request failures."""
        logger.error(
            "Request failed: %s - %s",
            failure.request.url,
            str(failure.value),
            exc_info=failure.value
        )
        self.failed_count += 1
        self.progress.update_progress(advance=1, failed=True) 
