"""Enhanced terminal user interface for the bunkrr package."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

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
    DownloadColumn
)
from rich.table import Table
from rich.text import Text
from rich.style import Style
from rich.theme import Theme

# Custom theme for consistent styling
THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red",
    "success": "green",
    "progress.percentage": "cyan",
    "progress.download": "green",
    "progress.data.speed": "cyan",
    "url": "blue underline",
    "filename": "bright_cyan",
    "stats": "magenta"
})

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

class DownloadProgress:
    """Enhanced download progress tracking with rich UI."""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console(theme=THEME)
        self.stats = DownloadStats()
        self.current_album: Optional[str] = None
        
        # Create progress bars with enhanced columns
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="progress.download"),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            expand=True
        )
        
        # Create overall progress
        self.total_progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="progress.percentage"),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=self.console,
            expand=True
        )
        
        # Task IDs for progress tracking
        self.total_task_id = self.total_progress.add_task(
            "[bright_cyan]Overall Progress",
            total=None
        )
        self.current_task_id = None
        
    def start(self):
        """Start progress tracking."""
        self.stats.start_time = datetime.now()
        self.live = Live(
            self._generate_layout(),
            console=self.console,
            refresh_per_second=4
        )
        self.live.start()
        
    def stop(self):
        """Stop progress tracking and show summary."""
        self.live.stop()
        self._show_summary()
        
    def update_album(self, album_name: str, total_files: int):
        """Update current album information."""
        self.current_album = album_name
        self.stats.total_files += total_files
        self.total_progress.update(self.total_task_id, total=self.stats.total_files)
        
        # Create new progress bar for album
        if self.current_task_id:
            self.progress.remove_task(self.current_task_id)
        self.current_task_id = self.progress.add_task(
            f"[bright_cyan]{album_name}",
            total=total_files
        )
        
    def update_progress(self, advance: int = 1, downloaded: int = 0, failed: bool = False):
        """Update download progress."""
        if failed:
            self.stats.failed_files += advance
        else:
            self.stats.completed_files += advance
            self.stats.downloaded_size += downloaded
            
        self.progress.update(self.current_task_id, advance=advance)
        self.total_progress.update(self.total_task_id, advance=advance)
        self.live.update(self._generate_layout())
        
    def _generate_layout(self) -> Panel:
        """Generate rich layout with progress and stats."""
        # Create stats table
        stats_table = Table.grid(padding=1)
        stats_table.add_row(
            Text("Files:", style="stats"),
            Text(f"{self.stats.completed_files}/{self.stats.total_files}", style="info")
        )
        stats_table.add_row(
            Text("Success Rate:", style="stats"),
            Text(f"{self.stats.success_rate:.1f}%", style="info")
        )
        stats_table.add_row(
            Text("Downloaded:", style="stats"),
            Text(f"{self.stats.downloaded_size / 1024 / 1024:.1f} MB", style="info")
        )
        stats_table.add_row(
            Text("Elapsed Time:", style="stats"),
            Text(f"{self.stats.elapsed_time:.0f}s", style="info")
        )
        
        # Combine elements
        layout = Table.grid(padding=1)
        layout.add_row(Panel(stats_table, title="Download Statistics"))
        layout.add_row(Panel(self.total_progress))
        layout.add_row(Panel(self.progress, title=f"Current Album: {self.current_album or 'None'}"))
        
        return Panel(layout, title="Bunkrr Downloader", border_style="cyan")
        
    def _show_summary(self):
        """Show download summary."""
        summary = Table.grid(padding=1)
        summary.add_row(
            Text("Total Files:", style="stats"),
            Text(str(self.stats.total_files), style="info")
        )
        summary.add_row(
            Text("Successfully Downloaded:", style="stats"),
            Text(str(self.stats.completed_files), style="success")
        )
        summary.add_row(
            Text("Failed:", style="stats"),
            Text(str(self.stats.failed_files), style="error")
        )
        summary.add_row(
            Text("Total Downloaded:", style="stats"),
            Text(f"{self.stats.downloaded_size / 1024 / 1024:.1f} MB", style="info")
        )
        summary.add_row(
            Text("Total Time:", style="stats"),
            Text(f"{self.stats.elapsed_time:.1f}s", style="info")
        )
        summary.add_row(
            Text("Success Rate:", style="stats"),
            Text(f"{self.stats.success_rate:.1f}%", style="info")
        )
        
        self.console.print("\n")
        self.console.print(Panel(
            summary,
            title="Download Summary",
            border_style="cyan"
        )) 
