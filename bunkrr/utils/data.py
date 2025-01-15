"""Data utilities for the bunkrr package."""
import math
import mimetypes
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Union, Any, Callable

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn
)
from rich.table import Table

from ..core.logger import setup_logger

logger = setup_logger('bunkrr.data')

# Initialize mimetypes
mimetypes.init()

# Common media extensions
MEDIA_EXTENSIONS: Set[str] = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff',
    # Videos
    '.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv',
    # Archives
    '.zip', '.rar', '.7z', '.tar', '.gz'
}

@dataclass
class ProgressData:
    """Progress tracking data."""
    current: int
    total: int
    description: str
    start_time: float
    
    @property
    def percentage(self) -> float:
        """Calculate progress percentage."""
        return (self.current / self.total * 100) if self.total else 0

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

# Console instance for rich output
console = Console()

def format_size(size: Union[int, float]) -> str:
    """Format size in bytes to human readable string."""
    if size < 0:
        raise ValueError("Size must be non-negative")
    if size == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    base = 1024
    i = min(len(units) - 1, math.floor(math.log(size) / math.log(base)))
    
    return f"{size / (base ** i):.2f} {units[i]}"

def format_time(seconds: Union[int, float]) -> str:
    """Format time in seconds to human readable string."""
    if seconds < 0:
        raise ValueError("Time must be non-negative")
    if seconds == 0:
        return "0s"
    
    intervals: list[Tuple[str, int]] = [
        ('d', 86400),
        ('h', 3600),
        ('m', 60),
        ('s', 1)
    ]
    
    parts = []
    remaining = seconds
    
    for unit, count in intervals:
        value = int(remaining // count)
        if value > 0:
            parts.append(f"{value}{unit}")
            remaining %= count
    
    return " ".join(parts)

def format_rate(rate: Union[int, float]) -> str:
    """Format rate to human readable string."""
    if rate < 0:
        raise ValueError("Rate must be non-negative")
    return "0/s" if rate == 0 else f"{format_size(rate)}/s"

def create_progress_bar(
    description: str = "Downloading",
    total: Optional[int] = None,
    callback: Optional[Callable[[ProgressData], None]] = None
) -> Progress:
    """Create rich progress bar with consistent styling."""
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

def is_media_file(filename: str) -> bool:
    """Check if filename has a media extension."""
    try:
        ext = os.path.splitext(filename)[1].lower()
        return ext in MEDIA_EXTENSIONS
    except Exception as e:
        logger.error("Failed to check media file %s: %s", filename, str(e))
        return False 
