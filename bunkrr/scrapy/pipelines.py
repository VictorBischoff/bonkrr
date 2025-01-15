"""Scrapy pipelines for handling media downloads."""
import os
from pathlib import Path
from typing import Dict, Any, Optional

from scrapy import Spider
from scrapy.pipelines.files import FilesPipeline
from scrapy.http import Request

from ..core.config import DownloadConfig
from ..core.exceptions import ScrapyError
from ..core.logger import setup_logger
from ..ui.progress import ProgressTracker
from ..utils.filesystem import ensure_directory, get_unique_path, sanitize_filename

logger = setup_logger('bunkrr.scrapy.pipelines')

class BunkrFilesPipeline(FilesPipeline):
    """Pipeline for downloading media files."""
    
    def get_media_requests(self, item: Dict[str, Any], info):
        """Generate media download requests."""
        urls = item.get('file_urls', [])
        if not urls:
            logger.warning("No URLs found in item: %s", item)
            return []
            
        logger.debug("Processing URLs: %s", urls)
        return [Request(url) for url in urls]
        
    def file_path(self, request: Request, response=None, info=None, *, item=None):
        """Generate file path for downloaded media."""
        # Use provided filename or extract from URL
        filename = item.get('filename') if item else None
        if not filename:
            filename = os.path.basename(request.url)
            
        # Sanitize filename
        filename = sanitize_filename(filename)
        
        # Get album folder from item
        album_folder = item.get('album_title', 'unknown') if item else 'unknown'
        album_folder = sanitize_filename(album_folder)
        
        return os.path.join(album_folder, filename)

class BunkrDownloadPipeline:
    """Pipeline for handling media downloads."""
    
    def __init__(self, config: Optional[DownloadConfig] = None):
        """Initialize pipeline with configuration."""
        self.config = config or DownloadConfig()
        self.progress = ProgressTracker()
        self.current_album = None
        logger.info("Initialized BunkrDownloadPipeline with config: %s", self.config)
    
    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline instance from crawler."""
        config = getattr(crawler.spider, 'config', None)
        return cls(config)
    
    def open_spider(self, spider: Spider):
        """Initialize resources when spider opens."""
        logger.info("Opening spider: %s", spider.name)
        self.progress.start()
    
    def close_spider(self, spider: Spider):
        """Clean up resources when spider closes."""
        logger.info("Closing spider: %s", spider.name)
        self.progress.stop()
        
    def process_item(self, item: Dict[str, Any], spider: Spider) -> Dict[str, Any]:
        """Process a media item for download."""
        album_title = item['album_title']
        logger.debug("Processing item from album: %s", album_title)
        
        try:
            # Update progress tracking for new album
            if album_title != self.current_album:
                self.current_album = album_title
                self.progress.update_album(album_title, item.get('total_files', 1))
                logger.info("Switched to new album: %s", album_title)
            
            # Get parent folder from item or use default
            parent_folder = Path(item.get('parent_folder', self.config.downloads_path))
            logger.debug("Using parent folder: %s", parent_folder)
            
            # Create album folder
            album_folder = self._get_album_folder(album_title, parent_folder)
            logger.debug("Using album folder: %s", album_folder)
            
            try:
                ensure_directory(album_folder)
                logger.debug("Created album folder: %s", album_folder)
            except Exception as e:
                logger.error("Failed to create album folder: %s - %s", album_folder, str(e))
                raise ScrapyError(f"Failed to create album folder: {album_folder}", str(e))
            
            # Process downloaded files
            downloaded = sum(len(data) for data in item.get('files', []))
            if downloaded > 0:
                self.progress.update_progress(advance=1, downloaded=downloaded)
                logger.info(
                    "File downloaded: %s (%d bytes)",
                    item.get('filename', 'Unknown'),
                    downloaded
                )
            else:
                logger.error(
                    "No file downloaded for item: %s (URLs: %s)",
                    item.get('filename', 'Unknown'),
                    item.get('file_urls', [])
                )
                self.progress.update_progress(advance=1, failed=True)
            
            return item
            
        except Exception as e:
            logger.error(
                "Error processing item: %s - %s",
                item.get('url', 'Unknown URL'),
                str(e),
                exc_info=True
            )
            self.progress.update_progress(advance=1, failed=True)
            return item
            
    def _get_album_folder(self, album_title: str, parent_folder: Path) -> Path:
        """Generate unique album folder path."""
        # Sanitize album title
        safe_title = sanitize_filename(album_title)
        
        # Create full path
        album_path = parent_folder / safe_title
        
        # Get unique path if folder exists
        return get_unique_path(album_path)
