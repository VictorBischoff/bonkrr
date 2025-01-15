"""Media processor for Scrapy integration."""
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from scrapy.crawler import CrawlerRunner
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor, defer

from ..core.config import DownloadConfig
from ..core.logger import setup_logger, log_exception
from ..ui.progress import ProgressTracker
from .spiders.bunkr_spider import BunkrSpider

logger = setup_logger('bunkrr.scrapy.processor')

class MediaProcessor:
    """Handle media processing and downloading with Scrapy integration."""
    
    def __init__(self, config: DownloadConfig):
        """Initialize the media processor with optimized settings."""
        self.config = config
        self._progress = ProgressTracker()
        self._processed_urls: Set[str] = set()
        
        # Configure Scrapy settings
        settings = get_project_settings()
        settings_dict = self.config.scrapy.to_dict()
        settings_dict.update({
            'DOWNLOAD_DELAY': None,  # Disable Scrapy's built-in rate limiting
            'CONCURRENT_REQUESTS': self.config.max_concurrent_downloads,
            'CONCURRENT_REQUESTS_PER_DOMAIN': self.config.max_concurrent_downloads,
            'DOWNLOADER_MIDDLEWARES': {
                **settings_dict.get('DOWNLOADER_MIDDLEWARES', {}),
                'bunkrr.scrapy.middlewares.CustomRateLimiterMiddleware': 450,
            }
        })
        settings.update(settings_dict)
        
        self.crawler_runner = CrawlerRunner(settings)
        logger.info(
            "Initialized MediaProcessor with settings: %s",
            settings.copy_to_dict()
        )
        
    async def __aenter__(self):
        """Async context manager entry."""
        self._progress.start()  # Start progress tracking
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self._progress.stop()  # Stop progress tracking
        await self.cleanup()
    
    async def process_album(self, album_url: str, parent_folder: Path) -> Tuple[int, int]:
        """Process a single album URL using Scrapy."""
        logger.info("Processing album: %s", album_url)
        
        if album_url in self._processed_urls:
            logger.info("Skipping already processed URL: %s", album_url)
            return 0, 0
            
        self._processed_urls.add(album_url)
        
        try:
            # Create crawler with spider class and settings
            deferred = self.crawler_runner.crawl(
                BunkrSpider,
                config=self.config,
                start_urls=[album_url],
                parent_folder=parent_folder,
                progress_tracker=self._progress  # Pass progress tracker to spider
            )
            
            # Wait for crawler to finish
            await self._wait_for_crawler(deferred)
            
            # Get spider instance from crawler
            spider = deferred.result.spider
            
            # Log final stats
            logger.info(
                "Album processing completed: %d successful, %d failed",
                spider.media_count - spider.failed_count,
                spider.failed_count
            )
            
            return (
                spider.media_count - spider.failed_count,
                spider.failed_count
            )
            
        except Exception as e:
            log_exception(logger, e, f"processing album: {album_url}")
            return 0, 1
            
    async def _wait_for_crawler(self, deferred: defer.Deferred):
        """Wait for crawler to finish."""
        while not deferred.called:
            await asyncio.sleep(0.1)
            reactor.runUntilCurrent()
            
    async def cleanup(self):
        """Clean up resources."""
        logger.debug("Cleaning up MediaProcessor resources")
        # Stop reactor if running
        if reactor.running:
            reactor.stop() 
