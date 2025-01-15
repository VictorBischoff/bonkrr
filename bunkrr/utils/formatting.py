"""Formatting utilities for the bunkrr package."""
import math
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

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
from rich.text import Text

# Initialize console
console = Console()

def format_size(size: Union[int, float]) -> str:
    """Format size in bytes to human readable string."""
    if size == 0:
        return "0 B"
        
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    k = 1024
    i = math.floor(math.log(size) / math.log(k))
    
    return f"{size / (k ** i):.2f} {units[i]}"

def format_time(seconds: Union[int, float]) -> str:
    """Format time in seconds to human readable string."""
    if seconds < 0:
        return "0s"
        
    intervals = [
        ('d', 86400),    # days
        ('h', 3600),     # hours
        ('m', 60),       # minutes
        ('s', 1)         # seconds
    ]
    
    parts = []
    for unit, count in intervals:
        value = int(seconds // count)
        if value:
            parts.append(f"{value}{unit}")
            seconds -= value * count
            
    return " ".join(parts) if parts else "0s"

def format_rate(rate: Union[int, float]) -> str:
    """Format rate to human readable string."""
    if rate == 0:
        return "0/s"
        
    return f"{format_size(rate)}/s"

def format_progress(
    current: int,
    total: int,
    width: int = 40
) -> str:
    """Format progress bar string."""
    if total == 0:
        return "[" + " " * width + "] 0%"
        
    percent = min(100, int((current / total) * 100))
    filled = int((width * current) / total)
    bar = "=" * filled + "-" * (width - filled)
    
    return f"[{bar}] {percent}%"

def create_progress_bar(
    description: str = "Downloading",
    total: Optional[int] = None
) -> Progress:
    """Create rich progress bar."""
    return Progress(
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

def create_stats_table(stats: Dict[str, any]) -> Table:
    """Create rich table for statistics."""
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    # Add rows
    if 'total' in stats:
        table.add_row("Total", str(stats['total']))
    if 'completed' in stats:
        table.add_row("Completed", str(stats['completed']))
    if 'failed' in stats:
        table.add_row("Failed", str(stats['failed']))
    if 'skipped' in stats:
        table.add_row("Skipped", str(stats['skipped']))
    if 'bytes_downloaded' in stats:
        table.add_row("Downloaded", format_size(stats['bytes_downloaded']))
    if 'elapsed_time' in stats:
        table.add_row("Elapsed Time", format_time(stats['elapsed_time']))
    if 'success_rate' in stats:
        table.add_row("Success Rate", f"{stats['success_rate']:.1f}%")
    if 'average_speed' in stats:
        table.add_row("Average Speed", format_rate(stats['average_speed']))
    
    # Add errors if present
    if 'errors' in stats and stats['errors']:
        errors_table = Table(show_header=False, box=None)
        for error, count in stats['errors'].items():
            errors_table.add_row(f"{error}: {count}")
        table.add_row("Errors", errors_table)
    
    return table

def truncate_text(
    text: str,
    max_length: int,
    placeholder: str = "..."
) -> str:
    """Truncate text to maximum length."""
    if len(text) <= max_length:
        return text
        
    if max_length <= len(placeholder):
        return placeholder[:max_length]
        
    return text[:(max_length - len(placeholder))] + placeholder

def wrap_text(
    text: str,
    width: int,
    indent: str = ""
) -> List[str]:
    """Wrap text to specified width."""
    import textwrap
    return textwrap.wrap(
        text,
        width=width,
        initial_indent=indent,
        subsequent_indent=indent
    )

def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def highlight_matches(
    text: str,
    pattern: str,
    style: str = "bold red"
) -> Text:
    """Highlight regex pattern matches in text."""
    result = Text(text)
    try:
        for match in re.finditer(pattern, text):
            start, end = match.span()
            result.stylize(style, start, end)
    except re.error:
        pass
    return result

def format_duration(
    start: datetime,
    end: Optional[datetime] = None
) -> str:
    """Format duration between two timestamps."""
    if end is None:
        end = datetime.now()
        
    delta = end - start
    
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
        
    return " ".join(parts)

def format_table(
    headers: List[str],
    rows: List[List[str]],
    alignments: Optional[List[str]] = None
) -> str:
    """Format data as ASCII table."""
    if not rows:
        return ""
        
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    
    # Get alignments
    if alignments is None:
        alignments = ["<"] * len(headers)
    
    # Format header
    header = " | ".join(
        f"{h:{a}{w}}" for h, w, a in zip(headers, widths, alignments)
    )
    separator = "-+-".join("-" * w for w in widths)
    
    # Format rows
    formatted_rows = [
        " | ".join(
            f"{str(c):{a}{w}}" for c, w, a in zip(row, widths, alignments)
        )
        for row in rows
    ]
    
    return "\n".join([header, separator] + formatted_rows) 
