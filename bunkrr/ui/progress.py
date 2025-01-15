"""Progress tracking for the bunkrr package."""
from dataclasses import dataclass
from datetime import datetime
import threading
from typing import Dict, Optional
import humanize

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
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.completed_files + self.failed_files
        return (self.completed_files / total * 100) if total > 0 else 0
        
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

class ProgressTracker:
    """Singleton progress tracker for unified progress tracking."""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
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
    
    def stop(self):
        """Stop progress tracking and show summary."""
        if self.live:
            self.live.stop()
            self._show_summary()
            self.live = None
    
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
    
    def update_progress(self, advance: int = 1, downloaded: int = 0, failed: bool = False):
        """Update download progress."""
        if failed:
            self.stats.failed_files += advance
        else:
            self.stats.completed_files += advance
            self.stats.downloaded_size += downloaded
            
        if self.current_task_id:
            self.progress.update(self.current_task_id, advance=advance)
        self.total_progress.update(self.total_task_id, advance=advance)
        
        if self.live:
            self.live.update(self._generate_layout())
    
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
