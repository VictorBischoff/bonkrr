"""Download manager for the bunkrr package."""
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console

from .config import DownloadConfig
from .data_processing import MediaProcessor
from .logger import setup_logger, log_exception
from .user_input import InputHandler
from .ui import DownloadProgress

logger = setup_logger('bunkrr.downloader')

class Downloader:
    """Main downloader class with improved organization."""
    
    def __init__(self, config: Optional[DownloadConfig] = None):
        self.config = config or DownloadConfig()
        self.input_handler = InputHandler(self.config)
        self._running = True
        self._failed_urls = set()
        self._success_urls = set()
        self._progress = DownloadProgress()
        logger.info(
            "Initialized Downloader",
            extra={
                "config": {
                    "max_retries": self.config.max_retries,
                    "retry_delay": self.config.retry_delay,
                    "download_timeout": self.config.download_timeout
                }
            }
        )
        
    def cancel_downloads(self):
        """Cancel ongoing downloads."""
        self._running = False
        logger.info("Download process cancelled by user")
        
    async def cleanup(self):
        """Clean up resources."""
        logger.debug("Cleaning up downloader resources")
        # MediaProcessor handles its own cleanup
        
    async def run(self) -> Tuple[int, int]:
        """Run the download process with proper error handling."""
        logger.info("Starting download process")
        
        # Get URLs from user
        urls = await self.input_handler.get_urls()
        if not urls:
            logger.info("No valid URLs provided")
            return 0, 0
            
        logger.info("Processing %d URLs", len(urls))
        
        # Get download folder
        download_folder = self.input_handler.get_download_folder()
        if not download_folder:
            logger.error("No valid download folder provided")
            return 0, 0
            
        logger.info("Using download folder: %s", download_folder)
        
        total_success = 0
        total_failed = 0
        
        # Process each album with retry logic
        async with MediaProcessor(self.config) as processor:
            for i, url in enumerate(urls, 1):
                if not self._running:
                    logger.info("Download cancelled by user")
                    break
                    
                logger.info("Processing URL %d/%d: %s", i, len(urls), url)
                
                try:
                    # Skip if already processed
                    if url in self._success_urls:
                        logger.info("Skipping already successfully processed URL: %s", url)
                        continue
                    elif url in self._failed_urls:
                        logger.info("Skipping previously failed URL: %s", url)
                        continue
                    
                    # Process with retries
                    success, failed = await self._process_with_retry(
                        processor,
                        url,
                        download_folder
                    )
                    
                    total_success += success
                    total_failed += failed
                    
                    # Track processed URLs
                    if success > 0:
                        self._success_urls.add(url)
                        logger.info("Successfully processed URL: %s", url)
                    else:
                        self._failed_urls.add(url)
                        logger.warning("Failed to process URL: %s", url)
                        
                except Exception as e:
                    log_exception(logger, e, f"processing URL: {url}")
                    total_failed += 1
                    self._failed_urls.add(url)
                    
        logger.info(
            "Download process completed",
            extra={
                "stats": {
                    "total_success": total_success,
                    "total_failed": total_failed,
                    "success_rate": f"{(total_success / (total_success + total_failed)) * 100:.1f}%" if total_success + total_failed > 0 else "N/A"
                }
            }
        )
        return total_success, total_failed
        
    async def _process_with_retry(
        self,
        processor: MediaProcessor,
        url: str,
        download_folder: Path
    ) -> Tuple[int, int]:
        """Process a URL with retry logic."""
        retry_count = 0
        max_retries = self.config.max_retries
        
        while retry_count < max_retries:
            try:
                return await processor.process_album(url, download_folder)
                
            except Exception as e:
                retry_count += 1
                log_exception(
                    logger,
                    e,
                    f"processing {url} (retry {retry_count}/{max_retries})"
                )
                
                if retry_count < max_retries:
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                    
                return 0, 1  # Return as failed after max retries
                
        return 0, 1  # Should never reach here, but satisfy type checker
