"""Backoff utilities for retry handling."""
from typing import Dict, Optional
import random
import time
from collections import defaultdict


class ExponentialBackoff:
    """Implements exponential backoff with jitter for retries."""
    
    def __init__(
        self,
        initial: float = 1.0,
        maximum: float = 60.0,
        factor: float = 2.0,
        jitter: bool = True
    ):
        """Initialize backoff parameters.
        
        Args:
            initial: Initial delay in seconds
            maximum: Maximum delay in seconds
            factor: Multiplication factor for each retry
            jitter: Whether to add random jitter
        """
        self.initial = initial
        self.maximum = maximum
        self.factor = factor
        self.jitter = jitter
        
        self._attempts: Dict[str, int] = defaultdict(int)
        self._min_delays: Dict[str, float] = {}
        self._last_attempt: Dict[str, float] = defaultdict(float)
    
    def get_delay(self, key: str) -> float:
        """Calculate delay for next retry.
        
        Args:
            key: Unique identifier for the retry sequence
            
        Returns:
            Delay in seconds before next attempt
        """
        attempts = self._attempts[key]
        min_delay = self._min_delays.get(key, self.initial)
        
        # Calculate base delay
        delay = min(
            min_delay * (self.factor ** attempts),
            self.maximum
        )
        
        # Add jitter if enabled
        if self.jitter:
            delay = random.uniform(delay * 0.5, delay * 1.5)
        
        # Ensure we don't exceed maximum
        delay = min(delay, self.maximum)
        
        # Update attempt counter and last attempt time
        self._attempts[key] += 1
        self._last_attempt[key] = time.time()
        
        return delay
    
    def reset(self, key: str) -> None:
        """Reset retry state for key.
        
        Args:
            key: Unique identifier to reset
        """
        self._attempts.pop(key, None)
        self._min_delays.pop(key, None)
        self._last_attempt.pop(key, None)
    
    def set_min_delay(self, delay: float, key: Optional[str] = None) -> None:
        """Set minimum delay for a key or globally.
        
        Args:
            delay: Minimum delay in seconds
            key: Optional key to set delay for. If None, sets initial delay.
        """
        if key is None:
            self.initial = max(delay, self.initial)
        else:
            self._min_delays[key] = max(delay, self._min_delays.get(key, 0))
    
    def get_attempt_count(self, key: str) -> int:
        """Get number of attempts for key.
        
        Args:
            key: Unique identifier
            
        Returns:
            Number of retry attempts
        """
        return self._attempts.get(key, 0)
    
    def should_reset(self, key: str, window: float = 300) -> bool:
        """Check if retry state should be reset based on time window.
        
        Args:
            key: Unique identifier
            window: Time window in seconds
            
        Returns:
            True if state should be reset
        """
        last_attempt = self._last_attempt.get(key, 0)
        if last_attempt and time.time() - last_attempt > window:
            self.reset(key)
            return True
        return False
    
    def cleanup(self, max_age: float = 3600) -> None:
        """Remove old entries from tracking dictionaries.
        
        Args:
            max_age: Maximum age in seconds to keep entries
        """
        now = time.time()
        expired = {
            key for key, last_time in self._last_attempt.items()
            if now - last_time > max_age
        }
        
        for key in expired:
            self.reset(key) 
