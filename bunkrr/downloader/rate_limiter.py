"""Rate limiting implementation for the bunkrr package."""
import asyncio
import time
from typing import Optional, Deque
from collections import deque

from ..core.exceptions import RateLimitError
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.rate_limiter')

class RateLimiter:
    """Rate limiter using token bucket algorithm with optimized token allocation."""
    
    def __init__(self, requests_per_window: int, window_seconds: int):
        """Initialize rate limiter with window parameters."""
        if requests_per_window < 1:
            raise RateLimitError("requests_per_window must be at least 1")
        if window_seconds < 1:
            raise RateLimitError("window_seconds must be at least 1")
            
        self.rate = requests_per_window / window_seconds
        self.bucket_size = requests_per_window
        self.current_tokens = requests_per_window
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
        self._token_queue: Deque[float] = deque()
        self._window_size = window_seconds
        
        logger.info(
            "Initialized rate limiter: %d requests per %d seconds",
            requests_per_window,
            window_seconds
        )
    
    def _cleanup_tokens(self, now: float) -> None:
        """Remove expired tokens from queue."""
        while self._token_queue and self._token_queue[0] <= now - self._window_size:
            self._token_queue.popleft()
    
    def _add_tokens(self) -> None:
        """Add tokens based on time elapsed with optimized calculation."""
        now = time.monotonic()
        time_passed = now - self.last_update
        
        # Skip update if time passed is negligible
        if time_passed < 0.001:  # 1ms threshold
            return
            
        new_tokens = time_passed * self.rate
        
        # Only update if meaningful number of tokens would be added
        if new_tokens >= 0.1:  # 0.1 token threshold
            self.current_tokens = min(
                self.bucket_size,
                self.current_tokens + new_tokens
            )
            self.last_update = now
            
            logger.debug(
                "Added %.2f tokens, current: %.2f",
                new_tokens,
                self.current_tokens
            )
    
    async def acquire(self, tokens: float = 1.0) -> None:
        """Acquire tokens with optimized waiting strategy."""
        if tokens > self.bucket_size:
            raise RateLimitError(
                f"Requested tokens ({tokens}) exceed bucket size ({self.bucket_size})"
            )
            
        async with self._lock:
            now = time.monotonic()
            self._cleanup_tokens(now)
            
            # Check if we're within rate limit
            if len(self._token_queue) >= self.bucket_size:
                wait_time = self._token_queue[0] + self._window_size - now
                if wait_time > 0:
                    logger.debug("Rate limit exceeded, waiting %.2f seconds", wait_time)
                    await asyncio.sleep(wait_time)
                    now = time.monotonic()
            
            # Add new token timestamp
            self._token_queue.append(now)
            
            # Update token bucket
            self._add_tokens()
            
            # Wait if not enough tokens
            while self.current_tokens < tokens:
                wait_time = (tokens - self.current_tokens) / self.rate
                logger.debug(
                    "Waiting %.2f seconds for %.2f tokens",
                    wait_time,
                    tokens
                )
                await asyncio.sleep(wait_time)
                self._add_tokens()
            
            self.current_tokens -= tokens
            logger.debug(
                "Acquired %.2f tokens, remaining: %.2f",
                tokens,
                self.current_tokens
            )
    
    def get_tokens(self) -> float:
        """Get current number of available tokens."""
        self._add_tokens()
        return self.current_tokens
