"""Performance tests for connection pool and rate limiter."""
import asyncio
import time
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from bunkrr.data_processing import MediaProcessor, ConnectionMetrics
from bunkrr.config import DownloadConfig

@pytest.fixture
def config():
    """Create test configuration."""
    return DownloadConfig(
        max_concurrent_downloads=6,
        rate_limit=5,
        rate_window=60,
        retry_delay=10,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )

@pytest.mark.asyncio
async def test_connection_pool_performance(config):
    """Test connection pool performance under load."""
    async with MediaProcessor(config) as processor:
        # Mock successful responses
        async def mock_response(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate network latency
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.text = AsyncMock(return_value="test content")
            return mock_resp
        
        processor._session.request = AsyncMock(side_effect=mock_response)
        
        # Make concurrent requests
        start_time = time.monotonic()
        tasks = [
            processor._make_request('GET', f'https://bunkr.site/a/test{i}')
            for i in range(20)
        ]
        
        # Wait for all requests to complete
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.monotonic()
        
        # Get metrics
        metrics = await processor.get_connection_metrics()
        
        # Verify performance
        duration = end_time - start_time
        successful = sum(1 for r in responses if not isinstance(r, Exception))
        
        # Log performance metrics
        print(f"\nPerformance Test Results:")
        print(f"Total requests: {len(tasks)}")
        print(f"Successful requests: {successful}")
        print(f"Total duration: {duration:.2f}s")
        print(f"Requests per second: {len(tasks)/duration:.2f}")
        print("\nConnection Metrics:")
        for key, value in metrics.items():
            if isinstance(value, float):
                print(f"{key}: {value:.2f}")
            else:
                print(f"{key}: {value}")
        
        # Assert performance requirements
        assert successful == len(tasks), "All requests should succeed"
        assert duration < 5.0, "Should complete within 5 seconds"
        assert metrics['failed_connections'] == 0, "Should have no failed connections"

@pytest.mark.asyncio
async def test_rate_limiter_performance(config):
    """Test rate limiter performance and consistency."""
    processor = MediaProcessor(config)
    
    # Track request timestamps
    timestamps = []
    
    async def make_request():
        await processor._rate_limiter.acquire()
        timestamps.append(time.monotonic())
    
    # Make concurrent requests
    start_time = time.monotonic()
    tasks = [make_request() for _ in range(15)]
    await asyncio.gather(*tasks)
    end_time = time.monotonic()
    
    # Calculate time differences between requests
    diffs = [t2 - t1 for t1, t2 in zip(timestamps[:-1], timestamps[1:])]
    avg_diff = sum(diffs) / len(diffs)
    max_diff = max(diffs)
    min_diff = min(diffs)
    
    # Log timing metrics
    print(f"\nRate Limiter Performance:")
    print(f"Total requests: {len(tasks)}")
    print(f"Total duration: {end_time - start_time:.2f}s")
    print(f"Average time between requests: {avg_diff:.3f}s")
    print(f"Min time between requests: {min_diff:.3f}s")
    print(f"Max time between requests: {max_diff:.3f}s")
    
    # Verify rate limiting
    expected_min_time = config.rate_window / config.rate_limit
    assert min_diff >= expected_min_time * 0.8, \
        f"Minimum time between requests ({min_diff:.3f}s) should be at least {expected_min_time * 0.8:.3f}s"
    assert max_diff <= expected_min_time * 1.5, \
        f"Maximum time between requests ({max_diff:.3f}s) should be at most {expected_min_time * 1.5:.3f}s"

@pytest.mark.asyncio
async def test_concurrent_downloads_performance(config, tmp_path):
    """Test performance of concurrent downloads."""
    async with MediaProcessor(config) as processor:
        # Mock URL resolution
        async def mock_get_download_url(url):
            return f"https://cdn.bunkr.site/files/{url.split('/')[-1]}"
        processor._get_download_url = AsyncMock(side_effect=mock_get_download_url)
        
        # Mock file download
        async def mock_download_response(*args, **kwargs):
            await asyncio.sleep(0.2)  # Simulate download time
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.content.iter_chunked = AsyncMock(
                return_value=[b"test" * 256]  # 1KB chunks
            )
            return mock_resp
        
        processor._session.request = AsyncMock(side_effect=mock_download_response)
        
        # Prepare test files with valid Bunkr URLs
        test_files = [
            (f"https://bunkr.site/i/test{i}", tmp_path / f"file{i}.txt")
            for i in range(12)
        ]
        
        # Start downloads
        start_time = time.monotonic()
        tasks = [
            processor._download_file(url, path)
            for url, path in test_files
        ]
        
        # Wait for downloads to complete
        results = await asyncio.gather(*tasks)
        end_time = time.monotonic()
        
        # Get metrics
        metrics = await processor.get_connection_metrics()
        
        # Calculate statistics
        duration = end_time - start_time
        successful = sum(1 for success, _ in results if success)
        total_bytes = sum(size for _, size in results)
        
        # Log performance metrics
        print(f"\nDownload Performance Test Results:")
        print(f"Total files: {len(test_files)}")
        print(f"Successful downloads: {successful}")
        print(f"Total duration: {duration:.2f}s")
        print(f"Average download time: {duration/len(test_files):.2f}s")
        print(f"Total data transferred: {total_bytes/1024:.2f}KB")
        print(f"Transfer rate: {(total_bytes/1024)/duration:.2f}KB/s")
        print("\nConnection Pool Metrics:")
        for key, value in metrics.items():
            if isinstance(value, float):
                print(f"{key}: {value:.2f}")
            else:
                print(f"{key}: {value}")
        
        # Verify performance requirements
        assert successful == len(test_files), "All downloads should succeed"
        assert duration < 10.0, "Should complete within 10 seconds"
        assert metrics['failed_connections'] == 0, "Should have no failed connections" 
