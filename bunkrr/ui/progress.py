"""Progress tracking for the bunkrr package."""
from dataclasses import dataclass
from datetime import datetime
import threading
from typing import Dict, Optional, List
import humanize
import json
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
    TaskProgressColumn,
    DownloadColumn,
    MofNCompleteColumn
)
from rich.table import Table
from rich.text import Text
from rich.align import Align

from .themes import DEFAULT_THEME
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.progress')

@dataclass
class DownloadStats:
    """Statistics for download progress."""
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    total_size: int = 0
    downloaded_size: int = 0
    current_speed: float = 0.0
    start_time: Optional[datetime] = None
    
    # Track performance metrics
    download_speeds: List[float] = None
    download_times: List[float] = None
    failure_timestamps: List[float] = None
    
    def __post_init__(self):
        """Initialize tracking lists."""
        self.download_speeds = []
        self.download_times = []
        self.failure_timestamps = []
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.completed_files + self.failed_files
        rate = (self.completed_files / total * 100) if total > 0 else 0
        logger.debug(
            "Success rate calculated - Completed: %d, Failed: %d, Rate: %.2f%%",
            self.completed_files,
            self.failed_files,
            rate
        )
        return rate
        
    @property
    def elapsed_time(self) -> float:
        """Calculate elapsed time in seconds."""
        if not self.start_time:
            return 0
        return (datetime.now() - self.start_time).total_seconds()
    
    @property
    def formatted_downloaded_size(self) -> str:
        """Format downloaded size in human readable format."""
        return humanize.naturalsize(self.downloaded_size, binary=True)
    
    @property
    def formatted_elapsed_time(self) -> str:
        """Format elapsed time in human readable format."""
        return humanize.naturaldelta(self.elapsed_time)
    
    def get_performance_stats(self) -> Dict:
        """Get detailed performance statistics."""
        stats = {
            'avg_speed': sum(self.download_speeds) / len(self.download_speeds) if self.download_speeds else 0,
            'max_speed': max(self.download_speeds) if self.download_speeds else 0,
            'min_speed': min(self.download_speeds) if self.download_speeds else 0,
            'avg_download_time': sum(self.download_times) / len(self.download_times) if self.download_times else 0,
            'max_download_time': max(self.download_times) if self.download_times else 0,
            'min_download_time': min(self.download_times) if self.download_times else 0,
            'failure_rate_per_minute': (
                len(self.failure_timestamps) * 60 / self.elapsed_time
                if self.elapsed_time > 0 else 0
            )
        }
        
        logger.debug(
            "Performance stats calculated: %s",
            json.dumps(stats, indent=2)
        )
        return stats

class ProgressTracker:
    """Singleton progress tracker for unified progress tracking."""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                logger.info("Created new ProgressTracker instance")
            return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.console = Console(theme=DEFAULT_THEME)
            self.stats = DownloadStats()
            self.current_album = None
            self.album_items = {}
            self.live = None
            self._setup_progress_bars()
            self.initialized = True
            logger.info("Initialized ProgressTracker")
    
    def _setup_progress_bars(self):
        """Set up progress bars with enhanced columns."""
        self.progress = Progress(
            SpinnerColumn(style="progress.spinner"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                complete_style="progress.download",
                finished_style="bright_green",
                pulse_style="progress.download"
            ),
            MofNCompleteColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            expand=True
        )
        
        self.total_progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(
                complete_style="progress.percentage",
                finished_style="bright_green",
                pulse_style="progress.percentage"
            ),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=self.console,
            expand=True
        )
        
        self.total_task_id = self.total_progress.add_task(
            "[bright_white]Overall Progress",
            total=None
        )
        self.current_task_id = None
    
    def start(self):
        """Start progress tracking."""
        if not self.live:
            self.stats.start_time = datetime.now()
            self.live = Live(
                self._generate_layout(),
                console=self.console,
                refresh_per_second=4,
                transient=True
            )
            self.live.start()
            logger.info(
                "Started progress tracking at %s",
                self.stats.start_time.isoformat()
            )
    
    def stop(self):
        """Stop progress tracking and show summary."""
        if self.live:
            self.live.stop()
            self._show_summary()
            self.live = None
            
            # Log final statistics
            performance_stats = self.stats.get_performance_stats()
            logger.info(
                "Download session completed - Stats: %s",
                json.dumps({
                    'total_files': self.stats.total_files,
                    'completed_files': self.stats.completed_files,
                    'failed_files': self.stats.failed_files,
                    'total_size': self.stats.total_size,
                    'downloaded_size': self.stats.downloaded_size,
                    'elapsed_time': self.stats.elapsed_time,
                    'success_rate': self.stats.success_rate,
                    'performance': performance_stats
                }, indent=2)
            )
    
    def update_album(self, album_name: str, total_files: int):
        """Update current album information."""
        self.current_album = album_name
        self.album_items[album_name] = total_files
        self.stats.total_files += total_files
        self.total_progress.update(self.total_task_id, total=self.stats.total_files)
        
        if self.current_task_id:
            self.progress.remove_task(self.current_task_id)
        self.current_task_id = self.progress.add_task(
            f"[bright_white]Processing: [bright_cyan]{album_name}",
            total=total_files
        )
        
        if self.live:
            self.live.update(self._generate_layout())
        
        logger.info(
            "Started processing album - Name: %s, Files: %d, Total files: %d",
            album_name,
            total_files,
            self.stats.total_files
        )
    
    def update_progress(self, advance: int = 1, downloaded: int = 0, failed: bool = False):
        """Update download progress."""
        if advance < 0:
            logger.warning("Negative progress update ignored: %d", advance)
            return
            
        if downloaded < 0:
            logger.warning("Negative download size ignored: %d", downloaded)
            return
            
        start_time = time.time()
        
        try:
            if failed:
                self.stats.failed_files += advance
                self.stats.failure_timestamps.append(time.time())
                logger.warning(
                    "Download failed - Album: %s, Failed count: %d",
                    self.current_album,
                    self.stats.failed_files
                )
            else:
                self.stats.completed_files += advance
                self.stats.downloaded_size += downloaded
                
                # Track performance metrics
                download_time = time.time() - start_time
                if download_time > 0:  # Avoid division by zero
                    speed = downloaded / download_time
                    
                    self.stats.download_times.append(download_time)
                    self.stats.download_speeds.append(speed)
                    
                    logger.debug(
                        "Download completed - Album: %s, Size: %s, Speed: %.2f MB/s, Time: %.2fs",
                        self.current_album,
                        humanize.naturalsize(downloaded, binary=True),
                        speed / (1024 * 1024),
                        download_time
                    )
                
            # Update progress bars
            try:
                if self.current_task_id is not None:
                    self.progress.update(self.current_task_id, advance=advance)
                if self.total_task_id is not None:
                    self.total_progress.update(self.total_task_id, advance=advance)
            except Exception as e:
                logger.error("Failed to update progress bars: %s", str(e))
            
            # Log progress periodically
            total_processed = self.stats.completed_files + self.stats.failed_files
            if total_processed > 0 and total_processed % 10 == 0:
                logger.info(
                    "Download progress - Completed: %d, Failed: %d, Success rate: %.2f%%, "
                    "Downloaded: %s",
                    self.stats.completed_files,
                    self.stats.failed_files,
                    self.stats.success_rate,
                    self.stats.formatted_downloaded_size
                )
            
            # Update display
            if self.live:
                try:
                    self.live.update(self._generate_layout())
                except Exception as e:
                    logger.error("Failed to update display: %s", str(e))
                    # Try to recreate display if update fails
                    try:
                        if self.live:
                            self.live.stop()
                        self.live = Live(
                            self._generate_layout(),
                            console=self.console,
                            refresh_per_second=4,
                            transient=True
                        )
                        self.live.start()
                    except Exception as e2:
                        logger.error("Failed to recreate display: %s", str(e2))
                    
        except Exception as e:
            logger.error(
                "Error updating progress - Album: %s, Error: %s",
                self.current_album,
                str(e),
                exc_info=True
            )
    
    def _generate_layout(self) -> Panel:
        """Generate rich layout with progress and stats."""
        # Create stats table with improved formatting
        stats_table = Table.grid(padding=1)
        stats_table.add_row(
            Text("Files:", style="stats"),
            Text(f"{self.stats.completed_files}/{self.stats.total_files}", style="stats.value")
        )
        stats_table.add_row(
            Text("Success Rate:", style="stats"),
            Text(f"{self.stats.success_rate:.1f}%", 
                 style="summary.success" if self.stats.success_rate > 90 else "summary.error")
        )
        stats_table.add_row(
            Text("Downloaded:", style="stats"),
            Text(self.stats.formatted_downloaded_size, style="stats.value")
        )
        stats_table.add_row(
            Text("Elapsed Time:", style="stats"),
            Text(self.stats.formatted_elapsed_time, style="stats.value")
        )
        
        # Create layout with improved spacing and alignment
        layout = Table.grid(padding=1)
        layout.add_row(Panel(
            Align.center(stats_table),
            title="Download Statistics",
            border_style="panel.border",
            title_align="center"
        ))
        layout.add_row(Panel(
            self.total_progress,
            border_style="panel.border"
        ))
        layout.add_row(Panel(
            self.progress,
            title=f"Current Album: {self.current_album or 'None'}",
            border_style="panel.border",
            title_align="center"
        ))
        
        return Panel(
            layout,
            title="[summary.title]Bunkrr Downloader",
            border_style="panel.border",
            padding=(1, 2)
        )
    
    def _show_summary(self):
        """Show download summary with enhanced formatting."""
        summary = Table.grid(padding=1)
        summary.add_row(
            Text("Total Files:", style="stats"),
            Text(str(self.stats.total_files), style="stats.value")
        )
        summary.add_row(
            Text("Successfully Downloaded:", style="stats"),
            Text(str(self.stats.completed_files), style="summary.success")
        )
        summary.add_row(
            Text("Failed:", style="stats"),
            Text(str(self.stats.failed_files), style="summary.error")
        )
        summary.add_row(
            Text("Total Downloaded:", style="stats"),
            Text(self.stats.formatted_downloaded_size, style="summary.info")
        )
        summary.add_row(
            Text("Total Time:", style="stats"),
            Text(self.stats.formatted_elapsed_time, style="stats.value")
        )
        summary.add_row(
            Text("Success Rate:", style="stats"),
            Text(f"{self.stats.success_rate:.1f}%",
                 style="summary.success" if self.stats.success_rate > 90 else "summary.error")
        )
        
        self.console.print("\n")
        self.console.print(Panel(
            Align.center(summary),
            title="[summary.title]Download Summary",
            border_style="panel.border",
            padding=(1, 2)
        )) 
