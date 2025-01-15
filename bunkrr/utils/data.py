"""Data utilities for the bunkrr package."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
import json
import logging
import math
import mimetypes
import time
from collections import deque

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn
)

from ..core.logger import setup_logger

logger = setup_logger('bunkrr.data')

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
        """Add error occurrence."""
        self.errors[error] = self.errors.get(error, 0) + 1
    
    def to_dict(self) -> Dict:
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
    """Track rate of operations over time with enhanced monitoring."""
    
    def __init__(self, window_size: int = 60):
        """Initialize rate tracker with window size in seconds."""
        self.window_size = window_size
        self._events: List[Tuple[float, int]] = []
        self._wait_times: List[Tuple[float, float]] = []  # (timestamp, wait_time)
        self._rate_limit_hits = 0
        self._last_cleanup = time.time()
        
    def add_event(self, count: int = 1, wait_time: Optional[float] = None) -> None:
        """Add event occurrence with optional wait time."""
        now = time.time()
        self._events.append((now, count))
        
        if wait_time is not None and wait_time > 0:
            self._wait_times.append((now, wait_time))
            self._rate_limit_hits += 1
            
        # Periodic cleanup
        if now - self._last_cleanup >= 5.0:  # Cleanup every 5 seconds
            self._cleanup(now)
            self._last_cleanup = now
    
    def _cleanup(self, now: float) -> None:
        """Remove events outside window."""
        cutoff = now - self.window_size
        
        # Clean up events
        while self._events and self._events[0][0] < cutoff:
            self._events.pop(0)
            
        # Clean up wait times
        while self._wait_times and self._wait_times[0][0] < cutoff:
            self._wait_times.pop(0)
    
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
    
    def get_wait_time_stats(self) -> Dict[str, float]:
        """Get statistics about rate limit wait times."""
        if not self._wait_times:
            return {
                'avg_wait': 0.0,
                'max_wait': 0.0,
                'rate_limit_hits': 0,
                'rate_limit_ratio': 0.0
            }
            
        wait_times = [wt for _, wt in self._wait_times]
        total_requests = len(self._events)
        
        return {
            'avg_wait': sum(wait_times) / len(wait_times),
            'max_wait': max(wait_times),
            'rate_limit_hits': self._rate_limit_hits,
            'rate_limit_ratio': self._rate_limit_hits / total_requests if total_requests > 0 else 0.0
        }
    
    def reset(self) -> None:
        """Reset all tracking data."""
        self._events.clear()
        self._wait_times.clear()
        self._rate_limit_hits = 0
        self._last_cleanup = time.time()

console = Console()

def format_size(size: Union[int, float]) -> str:
    """Format size in human readable format."""
    if size < 0:
        raise ValueError("Size must be non-negative")
    if size == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    base = 1024
    i = min(len(units) - 1, math.floor(math.log(size) / math.log(base)))
    
    return f"{size / (base ** i):.2f} {units[i]}"

@dataclass
class ProgressData:
    """Progress data for callbacks."""
    current: int
    total: int
    description: str
    start_time: Optional[datetime] = None

def create_progress_bar(
    description: str,
    total: Optional[int] = None,
    callback: Optional[callable] = None
) -> Progress:
    """Create a progress bar with optional callback."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console
    )
    
    if callback:
        progress.start()
        task = progress.add_task(description, total=total)
        
        def update(current: int, total: int) -> None:
            progress.update(task, completed=current, total=total)
            callback(ProgressData(current, total, description, progress.start_time))
        
        progress.update_callback = update
    
    return progress

def get_media_type(filename: str) -> Optional[str]:
    """Get media type from filename."""
    try:
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            return None
        
        main_type = mime_type.split('/')[0]
        if main_type in {'image', 'video', 'application'}:
            return main_type
        
        return None
        
    except Exception as e:
        logger.error("Failed to get media type for %s: %s", filename, str(e))
        return None 
