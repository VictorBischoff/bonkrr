"""Statistics utilities for the bunkrr package."""
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..core.logger import setup_logger

logger = setup_logger('bunkrr.stats')

@dataclass
class DownloadStats:
    """Statistics for download operations."""
    
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    bytes_downloaded: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    errors: Dict[str, int] = field(default_factory=dict)
    
    def start(self) -> None:
        """Start tracking time."""
        self.start_time = time.time()
    
    def stop(self) -> None:
        """Stop tracking time."""
        self.end_time = time.time()
    
    @property
    def is_running(self) -> bool:
        """Check if tracking is active."""
        return self.start_time is not None and self.end_time is None
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if not self.start_time:
            return 0.0
            
        end = self.end_time or time.time()
        return end - self.start_time
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if not self.total:
            return 0.0
        return (self.completed / self.total) * 100
    
    @property
    def average_speed(self) -> float:
        """Calculate average download speed in bytes per second."""
        elapsed = self.elapsed_time
        if not elapsed:
            return 0.0
        return self.bytes_downloaded / elapsed
    
    def add_error(self, error: str) -> None:
        """Track error occurrence."""
        self.errors[error] = self.errors.get(error, 0) + 1
    
    def to_dict(self) -> Dict[str, any]:
        """Convert stats to dictionary."""
        return {
            'total': self.total,
            'completed': self.completed,
            'failed': self.failed,
            'skipped': self.skipped,
            'bytes_downloaded': self.bytes_downloaded,
            'elapsed_time': self.elapsed_time,
            'success_rate': self.success_rate,
            'average_speed': self.average_speed,
            'errors': dict(self.errors)
        }

class RateTracker:
    """Track rate of operations over time."""
    
    def __init__(self, window_size: int = 60):
        """Initialize rate tracker with window size in seconds."""
        self.window_size = window_size
        self._events: List[Tuple[float, int]] = []
    
    def add_event(self, count: int = 1) -> None:
        """Add event occurrence."""
        now = time.time()
        self._events.append((now, count))
        self._cleanup(now)
    
    def _cleanup(self, now: float) -> None:
        """Remove events outside window."""
        cutoff = now - self.window_size
        while self._events and self._events[0][0] < cutoff:
            self._events.pop(0)
    
    def get_rate(self) -> float:
        """Calculate current rate per second."""
        now = time.time()
        self._cleanup(now)
        
        if not self._events:
            return 0.0
            
        total = sum(count for _, count in self._events)
        window = now - self._events[0][0]
        
        if window <= 0:
            return 0.0
            
        return total / window

class ProgressTracker:
    """Track progress of operations."""
    
    def __init__(self):
        """Initialize progress tracker."""
        self.stats = DownloadStats()
        self.rate_tracker = RateTracker()
        self._last_update = 0.0
    
    def start(self) -> None:
        """Start tracking progress."""
        self.stats.start()
        logger.info("Started progress tracking")
    
    def stop(self) -> None:
        """Stop tracking progress."""
        self.stats.stop()
        logger.info(
            "Completed tracking - Success rate: %.1f%%, "
            "Average speed: %.2f MB/s",
            self.stats.success_rate,
            self.stats.average_speed / 1024 / 1024
        )
    
    def update(
        self,
        completed: Optional[int] = None,
        failed: Optional[int] = None,
        skipped: Optional[int] = None,
        bytes_downloaded: Optional[int] = None,
        error: Optional[str] = None
    ) -> None:
        """Update progress stats."""
        if completed:
            self.stats.completed += completed
            self.rate_tracker.add_event(completed)
            
        if failed:
            self.stats.failed += failed
            
        if skipped:
            self.stats.skipped += skipped
            
        if bytes_downloaded:
            self.stats.bytes_downloaded += bytes_downloaded
            
        if error:
            self.stats.add_error(error)
            
        # Log progress periodically
        now = time.time()
        if now - self._last_update >= 5.0:
            self._log_progress()
            self._last_update = now
    
    def _log_progress(self) -> None:
        """Log current progress."""
        if not self.stats.is_running:
            return
            
        rate = self.rate_tracker.get_rate()
        speed = self.stats.average_speed / 1024 / 1024  # MB/s
        
        logger.info(
            "Progress: %d/%d (%.1f%%) - Rate: %.1f/s - Speed: %.2f MB/s",
            self.stats.completed,
            self.stats.total,
            self.stats.success_rate,
            rate,
            speed
        )
        
        if self.stats.errors:
            logger.warning(
                "Errors: %s",
                ", ".join(
                    f"{error}: {count}"
                    for error, count in self.stats.errors.items()
                )
            ) 
