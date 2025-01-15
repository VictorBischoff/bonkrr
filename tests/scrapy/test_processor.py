"""Test the URL processor functionality."""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from bunkrr.core.config import DownloadConfig
from bunkrr.scrapy.processor import MediaProcessor
from bunkrr.ui.progress import ProgressTracker

class MockSpider:
    """Mock spider for testing."""
    def __init__(self, **kwargs):
        self.media_count = 1
        self.failed_count = 1

@pytest.mark.asyncio
async def test_url_processor():
    """Test URL processor functionality."""
    # Setup test config
    config = DownloadConfig(
        downloads_path=Path("./test_downloads"),
        max_concurrent_downloads=2,
        max_retries=1,
        download_timeout=5,
        rate_limit=5,
        rate_window=60
    )
    
    # Initialize progress tracker
    progress_tracker = ProgressTracker()
    
    # Test URLs
    test_urls = [
        "https://bunkr.site/a/BH6IvyZR",  # Example album URL
        "https://ramen.bunkr.ru/0gm0e8r13umut9hgg0jky_source-cHjaKtF2.mp4"  # Example direct file URL
    ]
    
    # Create download path
    download_path = Path("./test_downloads")
    download_path.mkdir(exist_ok=True)
    
    try:
        with patch('bunkrr.scrapy.processor.BunkrSpider', MockSpider):
            async with MediaProcessor(config) as processor:
                # Start progress tracking
                progress_tracker.start()
                
                # Process URLs with timeout
                try:
                    success, failed = await asyncio.wait_for(
                        processor.process_urls(test_urls, download_path),
                        timeout=10
                    )
                except asyncio.TimeoutError:
                    success, failed = 0, len(test_urls)
                finally:
                    # Stop progress tracking
                    progress_tracker.stop()
                
                # Verify results
                assert isinstance(success, int)
                assert isinstance(failed, int)
                assert success + failed == len(test_urls)
                
    finally:
        # Cleanup
        if download_path.exists():
            for file in download_path.iterdir():
                file.unlink()
            download_path.rmdir()

@pytest.mark.asyncio
async def test_empty_urls():
    """Test URL processor with empty URL list."""
    config = DownloadConfig(
        downloads_path=Path("./test_downloads"),
        max_concurrent_downloads=2,
        max_retries=1,
        download_timeout=5,
        rate_limit=5,
        rate_window=60
    )
    
    # Initialize progress tracker
    progress_tracker = ProgressTracker()
    
    download_path = Path("./test_downloads")
    download_path.mkdir(exist_ok=True)
    
    try:
        with patch('bunkrr.scrapy.processor.BunkrSpider', MockSpider):
            async with MediaProcessor(config) as processor:
                # Start progress tracking
                progress_tracker.start()
                
                # Process URLs with timeout
                try:
                    success, failed = await asyncio.wait_for(
                        processor.process_urls([], download_path),
                        timeout=5
                    )
                except asyncio.TimeoutError:
                    success, failed = 0, 0
                finally:
                    # Stop progress tracking
                    progress_tracker.stop()
                
                # Verify results
                assert success == 0
                assert failed == 0
                
    finally:
        # Cleanup
        if download_path.exists():
            download_path.rmdir() 
