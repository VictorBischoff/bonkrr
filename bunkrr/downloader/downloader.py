"""Download manager for handling media downloads."""
import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Counter
from collections import Counter, deque
import json
import humanize

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

class DownloadStats:
    """Track download statistics."""
    
    def __init__(self, window_size: int = 3600):  # 1 hour window
        self.window_size = window_size
        self.total_downloads = 0
        self.successful_downloads = 0
        self.failed_downloads = 0
        self.total_bytes = 0
        self.start_time = time.time()
        
        # Performance tracking
        self.download_times = deque()  # (timestamp, duration)
        self.download_sizes = deque()  # (timestamp, size)
        self.error_counts = Counter()
        self.status_counts = Counter()
        self.retry_counts = Counter()
        
        # Cleanup tracking
        self.last_cleanup = time.time()
    
    def add_download(self, size: int, duration: float, success: bool, status_code: Optional[int] = None) -> None:
        """Record download attempt."""
        now = time.time()
        self.total_downloads += 1
        
        if success:
            self.successful_downloads += 1
            self.total_bytes += size
            self.download_times.append((now, duration))
            self.download_sizes.append((now, size))
        else:
            self.failed_downloads += 1
        
        if status_code:
            self.status_counts[status_code] += 1
        
        # Cleanup old data periodically
        if now - self.last_cleanup > 60:  # Every minute
            self._cleanup(now)
    
    def add_error(self, error_type: str) -> None:
        """Record error occurrence."""
        self.error_counts[error_type] += 1
    
    def add_retry(self, url: str) -> None:
        """Record download retry."""
        self.retry_counts[url] += 1
    
    def _cleanup(self, now: float) -> None:
        """Remove old data outside window."""
        cutoff = now - self.window_size
        
        # Clean download times
        while self.download_times and self.download_times[0][0] < cutoff:
            self.download_times.popleft()
        
        # Clean download sizes
        while self.download_sizes and self.download_sizes[0][0] < cutoff:
            self.download_sizes.popleft()
        
        self.last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics."""
        now = time.time()
        self._cleanup(now)
        
        # Calculate statistics
        elapsed = now - self.start_time
        recent_times = [t[1] for t in self.download_times]
        recent_sizes = [s[1] for s in self.download_sizes]
        
        stats = {
            'total_downloads': self.total_downloads,
            'successful_downloads': self.successful_downloads,
            'failed_downloads': self.failed_downloads,
            'success_rate': (
                self.successful_downloads / self.total_downloads * 100
                if self.total_downloads > 0 else 0
            ),
            'total_bytes': self.total_bytes,
            'bytes_per_second': self.total_bytes / elapsed if elapsed > 0 else 0,
            'downloads_per_minute': self.total_downloads * 60 / elapsed if elapsed > 0 else 0,
            'avg_download_time': sum(recent_times) / len(recent_times) if recent_times else 0,
            'avg_download_size': sum(recent_sizes) / len(recent_sizes) if recent_sizes else 0,
            'status_codes': dict(self.status_counts),
            'error_types': dict(self.error_counts),
            'retry_counts': dict(self.retry_counts)
        }
        
        logger.debug(
            "Download statistics calculated: %s",
            json.dumps(stats, indent=2)
        )
        return stats

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
        self._stats = DownloadStats()
        
        logger.info(
            "Initialized Downloader - Config: %s",
            json.dumps({
                'rate_limit': self.config.rate_limit,
                'rate_window': self.config.rate_window,
                'max_concurrent_downloads': self.config.max_concurrent_downloads,
                'download_timeout': self.config.download_timeout
            })
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
        logger.info(
            "Downloader setup complete - Session timeout: %ds, Max connections: %d",
            self.config.download_timeout,
            self.config.max_concurrent_downloads
        )
        
    async def cleanup(self):
        """Clean up resources."""
        self._progress.stop()
        
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Closed aiohttp session")
        
        # Log final statistics
        stats = self._stats.get_stats()
        logger.info(
            "Download session completed - Stats: %s",
            json.dumps(stats, indent=2)
        )
            
    def stop(self):
        """Stop the downloader."""
        self._running = False
        logger.info(
            "Downloader stopped - Processed URLs: %d",
            len(self._processed_urls)
        )
        
    async def download_media(
        self,
        url: str,
        destination: Path,
        filename: Optional[str] = None
    ) -> bool:
        """Download media from URL to destination."""
        if not self._running:
            return False
            
        start_time = time.time()
        download_size = 0
        success = False
        status_code = None
        file_path = None
        
        # Normalize URL
        url = normalize_url(url)
        
        # Skip if already processed
        if url in self._processed_urls:
            logger.info(
                "Skipping already processed URL: %s",
                url
            )
            return True
            
        self._processed_urls.add(url)
        logger.debug(
            "Starting download - URL: %s, Destination: %s",
            url,
            destination
        )
        
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
            async with self._session.get(url, ssl=False) as response:
                status_code = response.status
                self._stats.status_counts[status_code] += 1
                
                if response.status == 200:
                    # Stream response to file
                    async with open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            if not self._running:
                                return False
                            await f.write(chunk)
                            download_size += len(chunk)
                            
                    success = True
                    duration = time.time() - start_time
                    
                    logger.info(
                        "Download successful - URL: %s, Size: %s, Duration: %.2fs, "
                        "Speed: %.2f MB/s",
                        url,
                        humanize.naturalsize(download_size, binary=True),
                        duration,
                        download_size / duration / (1024 * 1024)
                    )
                    return True
                    
                else:
                    logger.error(
                        "Download failed - URL: %s, Status: %d, Headers: %s",
                        url,
                        response.status,
                        json.dumps(dict(response.headers))
                    )
                    return False
                    
        except asyncio.CancelledError:
            logger.info("Download cancelled - URL: %s", url)
            self._stats.add_error('cancelled')
            return False
            
        except client_exceptions.ClientError as e:
            error_type = type(e).__name__
            self._stats.add_error(error_type)
            log_exception(
                logger,
                e,
                f"HTTP client error downloading {url}",
                error_type=error_type
            )
            return False
            
        except OSError as e:
            error_type = type(e).__name__
            self._stats.add_error(error_type)
            log_exception(
                logger,
                e,
                f"OS error downloading {url}",
                error_type=error_type,
                file_path=str(file_path) if file_path else None
            )
            return False
            
        except Exception as e:
            error_type = type(e).__name__
            self._stats.add_error(error_type)
            log_exception(
                logger,
                e,
                f"Unexpected error downloading {url}",
                error_type=error_type
            )
            return False
            
        finally:
            # Record statistics
            self._stats.add_download(
                size=download_size,
                duration=time.time() - start_time,
                success=success,
                status_code=status_code
            )
            
            # Log periodic statistics
            if self._stats.total_downloads % 10 == 0:  # Every 10 downloads
                stats = self._stats.get_stats()
                logger.info(
                    "Download progress - Success rate: %.2f%%, Avg speed: %.2f MB/s",
                    stats['success_rate'],
                    stats['bytes_per_second'] / (1024 * 1024)
                )
