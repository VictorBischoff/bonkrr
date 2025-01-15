"""Rate limiting implementation for the bunkrr package."""
import asyncio
import time
from typing import Optional, Deque, Dict
from collections import deque
import json

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
        
        # Initialize statistics
        self._stats = {
            'total_requests': 0,
            'total_wait_time': 0.0,
            'max_wait_time': 0.0,
            'rate_limit_hits': 0,
            'token_shortages': 0
        }
        
        logger.info(
            "Initialized rate limiter - Config: %s",
            json.dumps({
                'requests_per_window': requests_per_window,
                'window_seconds': window_seconds,
                'rate': self.rate,
                'bucket_size': self.bucket_size
            })
        )
    
    def _cleanup_tokens(self, now: float) -> int:
        """Remove expired tokens from queue."""
        initial_size = len(self._token_queue)
        while self._token_queue and self._token_queue[0] <= now - self._window_size:
            self._token_queue.popleft()
        
        cleaned = initial_size - len(self._token_queue)
        if cleaned > 0:
            logger.debug(
                "Cleaned %d expired tokens - Queue size: %d",
                cleaned,
                len(self._token_queue)
            )
        return cleaned
    
    def _add_tokens(self) -> None:
        """Add tokens based on time elapsed with optimized calculation."""
        now = time.monotonic()
        time_passed = now - self.last_update
        
        # Skip update if time passed is negligible
        if time_passed < 0.001:  # 1ms threshold
            return
            
        new_tokens = time_passed * self.rate
        old_tokens = self.current_tokens
        
        # Only update if meaningful number of tokens would be added
        if new_tokens >= 0.1:  # 0.1 token threshold
            self.current_tokens = min(
                self.bucket_size,
                self.current_tokens + new_tokens
            )
            self.last_update = now
            
            logger.debug(
                "Token update - Added: %.2f, Previous: %.2f, Current: %.2f, Time passed: %.3fs",
                new_tokens,
                old_tokens,
                self.current_tokens,
                time_passed
            )
    
    async def acquire(self, tokens: float = 1.0) -> None:
        """Acquire tokens with optimized waiting strategy."""
        if tokens > self.bucket_size:
            raise RateLimitError(
                f"Requested tokens ({tokens}) exceed bucket size ({self.bucket_size})"
            )
        
        start_time = time.monotonic()
        self._stats['total_requests'] += 1
        
        async with self._lock:
            now = time.monotonic()
            cleaned_tokens = self._cleanup_tokens(now)
            
            # Check if we're within rate limit
            if len(self._token_queue) >= self.bucket_size:
                wait_time = self._token_queue[0] + self._window_size - now
                if wait_time > 0:
                    self._stats['rate_limit_hits'] += 1
                    logger.warning(
                        "Rate limit exceeded - Waiting: %.2fs, Queue size: %d/%d, "
                        "Rate limit hits: %d",
                        wait_time,
                        len(self._token_queue),
                        self.bucket_size,
                        self._stats['rate_limit_hits']
                    )
                    await asyncio.sleep(wait_time)
                    now = time.monotonic()
            
            # Add new token timestamp
            self._token_queue.append(now)
            
            # Update token bucket
            self._add_tokens()
            
            # Wait if not enough tokens
            total_wait = 0.0
            while self.current_tokens < tokens:
                self._stats['token_shortages'] += 1
                wait_time = (tokens - self.current_tokens) / self.rate
                total_wait += wait_time
                
                logger.debug(
                    "Token shortage - Waiting: %.2fs, Required: %.2f, Available: %.2f, "
                    "Shortages: %d",
                    wait_time,
                    tokens,
                    self.current_tokens,
                    self._stats['token_shortages']
                )
                
                await asyncio.sleep(wait_time)
                self._add_tokens()
            
            self.current_tokens -= tokens
            
            # Update statistics
            request_time = time.monotonic() - start_time
            self._stats['total_wait_time'] += total_wait
            self._stats['max_wait_time'] = max(
                self._stats['max_wait_time'],
                request_time
            )
            
            # Log detailed acquisition info
            logger.info(
                "Token acquisition completed - Stats: %s",
                json.dumps({
                    'tokens_requested': tokens,
                    'tokens_remaining': self.current_tokens,
                    'queue_size': len(self._token_queue),
                    'wait_time': total_wait,
                    'request_time': request_time,
                    'cleaned_tokens': cleaned_tokens
                })
            )
            
            # Log statistics periodically
            if self._stats['total_requests'] % 100 == 0:  # Every 100 requests
                self._log_statistics()
    
    def _log_statistics(self) -> None:
        """Log rate limiter statistics."""
        avg_wait = (
            self._stats['total_wait_time'] / self._stats['total_requests']
            if self._stats['total_requests'] > 0
            else 0.0
        )
        
        logger.info(
            "Rate limiter statistics - %s",
            json.dumps({
                'total_requests': self._stats['total_requests'],
                'rate_limit_hits': self._stats['rate_limit_hits'],
                'token_shortages': self._stats['token_shortages'],
                'avg_wait_time': avg_wait,
                'max_wait_time': self._stats['max_wait_time'],
                'current_queue_size': len(self._token_queue),
                'current_tokens': self.current_tokens
            })
        )
    
    def get_tokens(self) -> float:
        """Get current number of available tokens."""
        self._add_tokens()
        logger.debug(
            "Token check - Available: %.2f, Queue size: %d",
            self.current_tokens,
            len(self._token_queue)
        )
        return self.current_tokens
