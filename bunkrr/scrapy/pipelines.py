"""Scrapy pipelines for handling media downloads."""
import os
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

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
    """Pipeline for downloading media files with optimized handling."""
    
    def get_media_requests(self, item: Dict[str, Any], info):
        """Generate media download requests."""
        urls = item.get('file_urls', [])
        if not urls:
            logger.warning("No URLs found in item: %s", item)
            return []
            
        # Create requests with optimized settings
        requests = []
        for url in urls:
            # Parse URL to set appropriate headers
            parsed_url = urlparse(url)
            headers = {
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Host': parsed_url.netloc,
                'Referer': item.get('source_url', ''),
                'User-Agent': 'Mozilla/5.0'
            }
            
            # Add video-specific headers
            if item.get('media_type') == 'video':
                headers.update({
                    'Accept-Range': 'bytes',
                    'Range': 'bytes=0-'
                })
            
            requests.append(Request(
                url=url,
                headers=headers,
                meta={'media_info': item},
                dont_filter=True,
                priority=1 if item.get('media_type') == 'video' else 0
            ))
        
        logger.debug("Created %d download requests for item", len(requests))
        return requests
        
    def file_path(self, request: Request, response=None, info=None, *, item=None):
        """Generate optimized file path for downloaded media."""
        media_info = request.meta.get('media_info', {})
        album_title = media_info.get('album_title', 'unknown')
        filename = media_info.get('filename')
        
        if not filename:
            # Extract filename from URL if not provided
            filename = os.path.basename(request.url)
        
        # Sanitize both album title and filename
        safe_album = sanitize_filename(album_title)
        safe_filename = sanitize_filename(filename)
        
        # Create path
        return os.path.join(safe_album, safe_filename)
    
    def media_downloaded(self, response, request, info, *, item=None):
        """Handle successful media download."""
        media_info = request.meta.get('media_info', {})
        logger.info(
            "Successfully downloaded media from %s (%s bytes)",
            request.url,
            len(response.body)
        )
        return super().media_downloaded(response, request, info, item=item)
    
    def media_failed(self, failure, request, info):
        """Handle failed media download."""
        logger.error(
            "Failed to download media from %s: %s",
            request.url,
            str(failure.value)
        )
        return super().media_failed(failure, request, info)

class BunkrDownloadPipeline:
    """Pipeline for handling media downloads with progress tracking."""
    
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
        """Process media item with optimized handling."""
        try:
            album_title = item.get('album_title', 'unknown')
            
            # Update progress tracking
            if album_title != self.current_album:
                self.current_album = album_title
                logger.info("Processing album: %s", album_title)
            
            # Create album folder
            album_folder = self._get_album_folder(
                album_title,
                self.config.downloads_path
            )
            
            # Update item with folder information
            item['album_folder'] = str(album_folder)
            
            # Update progress
            self.progress.update(completed=1)
            logger.debug(
                "Processed item from album %s: %s",
                album_title,
                item.get('filename', 'unknown')
            )
            
            return item
            
        except Exception as e:
            logger.error(
                "Failed to process item from album %s: %s",
                album_title,
                str(e),
                exc_info=True
            )
            self.progress.update(failed=1)
            raise ScrapyError(f"Failed to process item from album: {album_title}", str(e))
    
    def _get_album_folder(self, album_title: str, parent_folder: Path) -> Path:
        """Generate unique album folder path."""
        # Sanitize album title
        safe_title = sanitize_filename(album_title)
        
        # Create full path
        album_path = parent_folder / safe_title
        
        try:
            # Get unique path if folder exists
            unique_path = get_unique_path(album_path)
            
            # Create directory if it doesn't exist
            unique_path.mkdir(parents=True, exist_ok=True)
            
            # Log directory creation
            if unique_path != album_path:
                logger.info(
                    "Using alternate folder name due to existing directory: %s -> %s",
                    album_path,
                    unique_path
                )
            
            return unique_path
            
        except Exception as e:
            logger.error("Failed to create album folder: %s - %s", album_path, str(e))
            raise ScrapyError(f"Failed to create album folder: {album_path}", str(e))
