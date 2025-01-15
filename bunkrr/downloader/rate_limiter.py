"""Rate limiting implementation for the bunkrr package."""
import asyncio
import time
from typing import Optional

from ..core.exceptions import RateLimitError
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.rate_limiter')

class RateLimiter:
    """Rate limiter using leaky bucket algorithm."""
    
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
        
        logger.info(
            "Initialized rate limiter: %d requests per %d seconds",
            requests_per_window,
            window_seconds
        )
    
    def _add_tokens(self) -> None:
        """Add tokens based on time elapsed."""
        now = time.monotonic()
        time_passed = now - self.last_update
        new_tokens = time_passed * self.rate
        
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
        """Acquire tokens, waiting if necessary."""
        if tokens > self.bucket_size:
            raise RateLimitError(
                f"Requested tokens ({tokens}) exceed bucket size ({self.bucket_size})"
            )
            
        async with self._lock:
            while self.current_tokens < tokens:
                self._add_tokens()
                if self.current_tokens < tokens:
                    wait_time = (tokens - self.current_tokens) / self.rate
                    logger.debug(
                        "Waiting %.2f seconds for %.2f tokens",
                        wait_time,
                        tokens
                    )
                    await asyncio.sleep(wait_time)
                    continue
                    
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
