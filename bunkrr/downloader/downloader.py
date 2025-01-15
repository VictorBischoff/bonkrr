"""Download manager for handling media downloads."""
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from aiohttp import (
    ClientSession, 
    ClientTimeout, 
    client_exceptions, 
    TCPConnector
)

from ..core.config import DownloadConfig
from ..core.logger import setup_logger, log_exception
from ..core.exceptions import DownloadError
from ..ui.progress import ProgressTracker
from .rate_limiter import RateLimiter
from ..utils.storage import (
    ensure_directory, get_file_size,
    get_unique_path, sanitize_filename
)
from ..utils.network import HTTPClient, HTTPConfig, normalize_url

logger = setup_logger('bunkrr.downloader')

class Downloader:
    """Handle concurrent media downloads with rate limiting."""
    
    def __init__(self, config: DownloadConfig):
        """Initialize downloader with configuration."""
        self.config = config
        self._progress = ProgressTracker()
        self._processed_urls: Set[str] = set()
        self._rate_limiter = RateLimiter(
            requests_per_window=self.config.rate_limit,
            window_seconds=self.config.rate_window
        )
        self._session: Optional[ClientSession] = None
        self._running = True
        
        logger.info(
            "Initialized Downloader with config: %s",
            self.config
        )
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.setup()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()
        
    async def setup(self):
        """Set up resources."""
        # Create session with connection pooling
        timeout = ClientTimeout(total=self.config.download_timeout)
        connector = TCPConnector(
            limit=self.config.max_concurrent_downloads,
            enable_cleanup_closed=True
        )
        self._session = ClientSession(
            timeout=timeout,
            connector=connector
        )
        self._progress.start()
        logger.debug("Downloader resources initialized")
        
    async def cleanup(self):
        """Clean up resources."""
        self._progress.stop()
        
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("Closed aiohttp session")
            
    def stop(self):
        """Stop the downloader."""
        self._running = False
        logger.info("Downloader stopped")
        
    async def download_media(
        self,
        url: str,
        destination: Path,
        filename: Optional[str] = None
    ) -> bool:
        """Download media from URL to destination."""
        if not self._running:
            return False
            
        # Normalize URL
        url = normalize_url(url)
        
        # Skip if already processed
        if url in self._processed_urls:
            logger.info("Skipping already processed URL: %s", url)
            return True
            
        self._processed_urls.add(url)
        logger.debug("Processing URL: %s", url)
        
        try:
            # Ensure destination exists
            ensure_directory(destination)
            
            # Generate filename if not provided
            if not filename:
                filename = url.split('/')[-1]
            filename = sanitize_filename(filename)
            
            # Get unique path
            file_path = get_unique_path(destination / filename)
            
            # Acquire rate limit token
            await self._rate_limiter.acquire()
            
            # Download file
            async with self._session.get(url) as response:
                if response.status == 200:
                    # Stream response to file
                    async with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            if not self._running:
                                return False
                            await f.write(chunk)
                            
                    logger.info("Successfully downloaded: %s", file_path)
                    return True
                    
                else:
                    logger.error(
                        "Failed to download %s: HTTP %d",
                        url,
                        response.status
                    )
                    return False
                    
        except asyncio.CancelledError:
            logger.info("Download cancelled: %s", url)
            return False
            
        except Exception as e:
            log_exception(logger, e, f"downloading {url}")
            return False 
