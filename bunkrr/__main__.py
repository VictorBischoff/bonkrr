"""Main entry point for the bunkrr package with improved error handling and configuration."""
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.progress import Progress

from .config import DownloadConfig
from .downloader import Downloader
from .logger import setup_logger

logger = setup_logger('bunkrr')

class DownloaderApp:
    """Main application class for Bunkr downloader."""
    
    def __init__(self, config: DownloadConfig):
        self.config = config
        self.downloader = Downloader(config)
        self.console = Console()
        self._shutdown = False
        self._tasks: List[asyncio.Task] = []
        
        # Ensure downloads directory exists
        self.config.downloads_path.mkdir(parents=True, exist_ok=True)
        
        logger.info("Initialized DownloaderApp with configuration:")
        logger.info("Max concurrent downloads: %d", config.max_concurrent_downloads)
        logger.info("Rate limit: %d requests per %ds", config.rate_limit, config.rate_window)
        logger.info("Download path: %s", config.downloads_path)

    def _handle_signal(self, signum, frame):
        """Handle interrupt signals."""
        if self._shutdown:
            logger.warning("\nForced shutdown, terminating immediately...")
            sys.exit(1)
            
        self._shutdown = True
        logger.info("\nReceived interrupt signal, shutting down gracefully...")
        
        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

    async def run(self) -> Tuple[int, int]:
        """Run the downloader with proper signal handling."""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        
        try:
            # Create main download task
            main_task = asyncio.create_task(self.downloader.run())
            self._tasks.append(main_task)
            
            # Wait for completion or cancellation
            success, failed = await main_task
            
            return success, failed
            
        except asyncio.CancelledError:
            logger.info("Download process cancelled by user")
            return 0, 0
            
        except Exception as e:
            logger.error("Fatal error: %r", e)
            return 0, 0
            
        finally:
            # Clean up
            try:
                await self.downloader.cleanup()
                logger.info("Cleanup completed")
            except Exception as e:
                logger.error("Error during cleanup: %r", e)

def main():
    """Entry point for the Bunkr downloader."""
    config = DownloadConfig()
    app = DownloaderApp(config)
    
    try:
        success, failed = asyncio.run(app.run())
        sys.exit(0 if success > 0 or failed == 0 else 1)
    except KeyboardInterrupt:
        logger.info("\nDownload cancelled by user")
        sys.exit(0)

if __name__ == '__main__':
    main()
