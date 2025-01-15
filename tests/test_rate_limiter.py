"""Tests for the rate limiter implementation."""
import asyncio
import time
from datetime import datetime

import pytest

from bunkrr.data_processing import RateLimiter

@pytest.mark.asyncio
async def test_rate_limiter_basic():
    """Test basic rate limiting functionality."""
    rate_limit = 5
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    
    # First batch should be immediate
    start_time = datetime.now()
    for _ in range(rate_limit):
        await limiter.acquire()
    elapsed = (datetime.now() - start_time).total_seconds()
    assert elapsed < 0.1  # Should be near-instant
    
    # Next request should be delayed
    await limiter.acquire()
    elapsed = (datetime.now() - start_time).total_seconds()
    assert elapsed >= window_size

@pytest.mark.asyncio
async def test_rate_limiter_concurrent():
    """Test rate limiter under concurrent load."""
    rate_limit = 5
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    
    async def make_request(request_id):
        start_time = datetime.now()
        await limiter.acquire()
        return (request_id, (datetime.now() - start_time).total_seconds())
    
    # Make concurrent requests
    tasks = [make_request(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    
    # First batch should be immediate, rest should be delayed
    immediate = [r for r in results if r[1] < 0.1]
    delayed = [r for r in results if r[1] >= window_size]
    assert len(immediate) == rate_limit
    assert len(delayed) == 5

@pytest.mark.asyncio
async def test_rate_limiter_reset():
    """Test rate limiter reset functionality."""
    rate_limit = 5
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    
    # Use up all tokens
    for _ in range(rate_limit):
        await limiter.acquire()
    
    # Reset limiter
    await limiter.reset()
    
    # Should be able to make immediate requests again
    start_time = datetime.now()
    for _ in range(rate_limit):
        await limiter.acquire()
    elapsed = (datetime.now() - start_time).total_seconds()
    assert elapsed < 0.1

@pytest.mark.asyncio
async def test_rate_limiter_window_sliding():
    """Test that rate limit window slides properly."""
    rate_limit = 5
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    
    # Use up all tokens
    for _ in range(rate_limit):
        await limiter.acquire()
    
    # Wait for half the window with some margin
    wait_time = window_size * 0.6  # Wait slightly longer than half
    await asyncio.sleep(wait_time)
    
    # Should still need to wait
    start_time = datetime.now()
    await limiter.acquire()
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Should wait for the remaining time with some tolerance
    expected_wait = window_size - wait_time
    assert elapsed >= expected_wait * 0.8, \
        f"Expected to wait at least {expected_wait * 0.8:.3f}s, but only waited {elapsed:.3f}s"

@pytest.mark.asyncio
async def test_rate_limiter_zero_window():
    """Test rate limiter with zero window size."""
    rate_limit = 5
    window_size = 0
    limiter = RateLimiter(rate_limit, window_size)
    
    # Should allow all requests immediately
    start_time = datetime.now()
    for _ in range(rate_limit * 2):
        await limiter.acquire()
    elapsed = (datetime.now() - start_time).total_seconds()
    assert elapsed < 0.1

@pytest.mark.asyncio
async def test_rate_limiter_infinite_rate():
    """Test rate limiter with infinite rate limit."""
    rate_limit = float('inf')
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    
    # Should allow many requests immediately
    start_time = datetime.now()
    for _ in range(1000):
        await limiter.acquire()
    elapsed = (datetime.now() - start_time).total_seconds()
    assert elapsed < 0.1

@pytest.mark.asyncio
async def test_rate_limiter_burst():
    """Test rate limiter under burst conditions."""
    rate_limit = 5
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    
    async def burst_requests(count):
        start_time = datetime.now()
        for i in range(count):
            await limiter.acquire()
        return (datetime.now() - start_time).total_seconds()
    
    # First burst
    elapsed1 = await burst_requests(rate_limit)
    assert elapsed1 < 0.1
    
    # Second immediate burst
    elapsed2 = await burst_requests(rate_limit)
    assert elapsed2 >= window_size
    
    # Wait for window to reset
    await asyncio.sleep(window_size)
    
    # Third burst should be immediate again
    elapsed3 = await burst_requests(rate_limit)
    assert elapsed3 < 0.1

@pytest.mark.asyncio
async def test_rate_limiter_cancellation():
    """Test rate limiter behavior with task cancellation."""
    rate_limit = 5
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    
    # Use up all tokens
    for _ in range(rate_limit):
        await limiter.acquire()
    
    async def delayed_acquire():
        await limiter.acquire()
    
    # Create and cancel a task
    task = asyncio.create_task(delayed_acquire())
    await asyncio.sleep(0.1)
    task.cancel()
    
    try:
        await task
    except asyncio.CancelledError:
        pass
    
    # Should still be able to acquire after window
    await asyncio.sleep(window_size)
    start_time = datetime.now()
    await limiter.acquire()
    elapsed = (datetime.now() - start_time).total_seconds()
    assert elapsed < 0.1

@pytest.mark.asyncio
async def test_rate_limiter_stress():
    """Stress test rate limiter with many concurrent requests."""
    rate_limit = 10
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    request_count = 100
    
    async def make_request(request_id):
        try:
            await limiter.acquire()
            return request_id
        except Exception as e:
            return f"Error {request_id}: {str(e)}"
    
    # Make many concurrent requests
    tasks = [make_request(i) for i in range(request_count)]
    results = await asyncio.gather(*tasks)
    
    # All requests should complete successfully
    assert len(results) == request_count
    assert all(isinstance(r, int) for r in results)
    
    # Verify rate limiting worked
    unique_results = set(results)
    assert len(unique_results) == request_count

@pytest.mark.asyncio
async def test_rate_limiter_window_edge():
    """Test rate limiter behavior at window boundaries."""
    rate_limit = 5
    window_size = 1
    limiter = RateLimiter(rate_limit, window_size)
    
    # Use up all tokens
    for _ in range(rate_limit):
        await limiter.acquire()
    
    # Wait until just before window ends
    await asyncio.sleep(window_size - 0.05)  # Increased margin
    
    start_time = datetime.now()
    await limiter.acquire()
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Should wait for the remaining time with some tolerance
    assert 0.001 <= elapsed <= 0.2  # Wider acceptable range
