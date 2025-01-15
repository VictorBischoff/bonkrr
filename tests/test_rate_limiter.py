"""Tests for the rate limiter implementation."""
import asyncio
import pytest
import time
from bunkrr.rate_limiter import RateLimiter

@pytest.mark.asyncio
async def test_rate_limiter_initialization():
    """Test rate limiter initialization."""
    requests_per_window = 5
    window_seconds = 60
    rate_limiter = RateLimiter(requests_per_window, window_seconds)
    
    assert rate_limiter.rate == requests_per_window / window_seconds
    assert rate_limiter.bucket_size == requests_per_window
    assert rate_limiter.current_tokens == requests_per_window

@pytest.mark.asyncio
async def test_token_acquisition():
    """Test basic token acquisition."""
    rate_limiter = RateLimiter(5, 60)  # 5 requests per 60 seconds
    
    # Should be able to acquire 5 tokens immediately
    for _ in range(5):
        await rate_limiter.acquire()
    
    # Verify tokens are depleted
    tokens = await rate_limiter.get_current_tokens()
    assert tokens < 1

@pytest.mark.asyncio
async def test_token_replenishment():
    """Test that tokens are replenished over time."""
    rate_limiter = RateLimiter(60, 60)  # 1 token per second
    
    # Use one token
    await rate_limiter.acquire()
    initial_tokens = await rate_limiter.get_current_tokens()
    
    # Wait for 1 second
    await asyncio.sleep(1)
    
    # Check that we have more tokens now
    current_tokens = await rate_limiter.get_current_tokens()
    assert current_tokens > initial_tokens

@pytest.mark.asyncio
async def test_rate_limiting():
    """Test that requests are properly rate limited."""
    rate_limiter = RateLimiter(2, 1)  # 2 requests per second
    
    # Record start time
    start_time = time.monotonic()
    
    # Make 4 requests (should take ~1.5 seconds)
    for _ in range(4):
        await rate_limiter.acquire()
    
    # Check duration
    duration = time.monotonic() - start_time
    assert duration >= 1.5  # Should take at least 1.5 seconds

@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test handling of concurrent requests."""
    rate_limiter = RateLimiter(2, 1)  # 2 requests per second
    
    async def make_request():
        await rate_limiter.acquire()
        return time.monotonic()
    
    # Launch 4 concurrent requests
    start_time = time.monotonic()
    results = await asyncio.gather(*[make_request() for _ in range(4)])
    
    # Check that requests were properly spaced
    timestamps = sorted(results)
    for i in range(1, len(timestamps)):
        time_diff = timestamps[i] - timestamps[i-1]
        assert time_diff >= 0.45  # Allow small margin for timing variations

@pytest.mark.asyncio
async def test_bucket_size_limit():
    """Test that bucket doesn't exceed maximum size."""
    rate_limiter = RateLimiter(5, 60)
    
    # Wait for potential token accumulation
    await asyncio.sleep(1)
    
    # Check that tokens don't exceed bucket size
    tokens = await rate_limiter.get_current_tokens()
    assert tokens <= rate_limiter.bucket_size
