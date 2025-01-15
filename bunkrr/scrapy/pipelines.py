"""Scrapy pipelines for handling media downloads."""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

from scrapy import Spider
from scrapy.pipelines.files import FilesPipeline
from scrapy.http import Request

from ..core.config import DownloadConfig
from ..core.exceptions import ScrapyError
from ..core.logger import setup_logger
from ..core.error_handler import ErrorHandler
from ..ui.progress import ProgressTracker
from ..utils.storage import (
    ensure_directory, get_file_size,
    sanitize_filename, get_unique_path
)

logger = setup_logger('bunkrr.scrapy.pipelines')

@dataclass
class MediaRequest:
    """Media download request configuration."""
    url: str
    media_type: str
    source_url: str
    filename: Optional[str] = None
    album_title: str = 'unknown'
    
    def get_headers(self) -> Dict[str, str]:
        """Get request headers based on media type."""
        headers = {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Host': urlparse(self.url).netloc,
            'Referer': self.source_url,
            'User-Agent': 'Mozilla/5.0'
        }
        
        if self.media_type == 'video':
            headers.update({
                'Accept-Range': 'bytes',
                'Range': 'bytes=0-'
            })
        
        return headers
    
    def to_request(self) -> Request:
        """Convert to Scrapy Request."""
        return Request(
            url=self.url,
            headers=self.get_headers(),
            meta={'media_info': self.__dict__},
            dont_filter=True,
            priority=1 if self.media_type == 'video' else 0
        )

class MediaPipeline(FilesPipeline):
    """Pipeline for downloading media files with enhanced error handling."""
    
    @ErrorHandler.wrap
    def get_media_requests(self, item: Dict[str, Any], info) -> List[Request]:
        """Generate media download requests."""
        urls = item.get('file_urls', [])
        if not urls:
            logger.warning("No URLs found in item: %s", item)
            return []
        
        requests = []
        for url in urls:
            media_request = MediaRequest(
                url=url,
                media_type=item.get('media_type', 'unknown'),
                source_url=item.get('source_url', ''),
                filename=item.get('filename'),
                album_title=item.get('album_title', 'unknown')
            )
            requests.append(media_request.to_request())
        
        logger.debug("Created %d download requests for item", len(requests))
        return requests
    
    @ErrorHandler.wrap
    def file_path(self, request: Request, response=None, info=None, *, item=None) -> str:
        """Generate file path for downloaded media."""
        media_info = request.meta.get('media_info', {})
        album = sanitize_filename(media_info.get('album_title', 'unknown'))
        filename = sanitize_filename(
            media_info.get('filename') or Path(request.url).name
        )
        
        return str(Path(album) / filename)
    
    @ErrorHandler.wrap
    def media_downloaded(self, response, request, info, *, item=None):
        """Handle successful media download."""
        media_info = request.meta.get('media_info', {})
        logger.info(
            "Downloaded media from %s (%s bytes)",
            request.url,
            len(response.body)
        )
        return super().media_downloaded(response, request, info, item=item)
    
    @ErrorHandler.wrap
    def media_failed(self, failure, request, info):
        """Handle failed media download."""
        logger.error(
            "Failed to download from %s: %s",
            request.url,
            str(failure.value)
        )
        return super().media_failed(failure, request, info)

class DownloadPipeline:
    """Pipeline for handling media downloads with progress tracking."""
    
    def __init__(self, config: Optional[DownloadConfig] = None):
        """Initialize pipeline with configuration."""
        self.config = config or DownloadConfig()
        self.progress = ProgressTracker()
        self.current_album: Optional[str] = None
        logger.debug("Initialized DownloadPipeline with config: %s", config)
    
    @classmethod
    def from_crawler(cls, crawler):
        """Create pipeline from crawler."""
        return cls(getattr(crawler.spider, 'config', None))
    
    def open_spider(self, spider: Spider) -> None:
        """Initialize resources when spider opens."""
        logger.info("Opening spider: %s", spider.name)
        self.progress.start()
    
    def close_spider(self, spider: Spider) -> None:
        """Clean up resources when spider closes."""
        logger.info("Closing spider: %s", spider.name)
        self.progress.stop()
    
    @ErrorHandler.wrap
    def process_item(self, item: Dict[str, Any], spider: Spider) -> Dict[str, Any]:
        """Process media item with progress tracking."""
        album_title = item.get('album_title', 'unknown')
        
        try:
            # Update progress tracking for new album
            if album_title != self.current_album:
                self.current_album = album_title
                logger.info("Processing album: %s", album_title)
            
            # Create album folder
            album_path = self._get_album_path(album_title)
            item['album_folder'] = str(album_path)
            
            # Update progress
            self.progress.update(completed=1)
            logger.debug(
                "Processed item: %s/%s",
                album_title,
                item.get('filename', 'unknown')
            )
            
            return item
            
        except Exception as e:
            self.progress.update(failed=1)
            raise ScrapyError(
                message=f"Failed to process item from album: {album_title}",
                details=str(e)
            )
    
    def _get_album_path(self, album_title: str) -> Path:
        """Get unique album folder path."""
        base_path = self.config.downloads_path / sanitize_filename(album_title)
        unique_path = get_unique_path(base_path)
        
        try:
            unique_path.mkdir(parents=True, exist_ok=True)
            
            if unique_path != base_path:
                logger.info(
                    "Using alternate path: %s -> %s",
                    base_path.name,
                    unique_path.name
                )
            
            return unique_path
            
        except Exception as e:
            logger.error("Failed to create album folder: %s", str(e))
            raise ScrapyError(
                message=f"Failed to create album folder: {base_path}",
                details=str(e)
            )
