"""Console UI components for the bunkrr package."""
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.text import Text

from .themes import DEFAULT_THEME
from ..core.exceptions import ValidationError

class ConsoleUI:
    """Console user interface for bunkrr."""
    
    def __init__(self):
        """Initialize console UI."""
        self.console = Console(theme=DEFAULT_THEME)
    
    def print_welcome(self):
        """Display welcome message."""
        welcome = Panel(
            Text(
                "Welcome to Bunkrr Downloader\n\n"
                "Enter URLs to download, one per line.\n"
                "Press Ctrl+D (Unix) or Ctrl+Z (Windows) when done.",
                style="info"
            ),
            title="Bunkrr",
            border_style="cyan"
        )
        self.console.print(welcome)
    
    def get_urls(self) -> List[str]:
        """Get URLs from user input."""
        urls = []
        try:
            while True:
                url = Prompt.ask("[cyan]Enter URL[/cyan]", console=self.console)
                if not url:
                    break
                urls.append(url)
        except (EOFError, KeyboardInterrupt):
            self.console.print()
        
        if not urls:
            self.console.print("[yellow]No URLs provided.[/yellow]")
        else:
            self.console.print(f"[green]Received {len(urls)} URLs.[/green]")
        
        return urls
    
    def get_download_path(self, default: Path) -> Optional[Path]:
        """Get download path from user."""
        try:
            path_str = Prompt.ask(
                "[cyan]Enter download path[/cyan]",
                default=str(default),
                console=self.console
            )
            return Path(path_str)
        except Exception as e:
            self.console.print(f"[red]Invalid path: {str(e)}[/red]")
            return None
    
    def confirm_action(self, message: str, default: bool = True) -> bool:
        """Get user confirmation for an action."""
        return Confirm.ask(
            f"[cyan]{message}[/cyan]",
            default=default,
            console=self.console
        )
    
    def print_error(self, error: Exception, context: str = ''):
        """Print error message."""
        if isinstance(error, ValidationError):
            self.console.print(
                f"[red]{context}: {error.message}[/red]",
                style="error"
            )
            if error.details:
                self.console.print(
                    f"[red]Details: {error.details}[/red]",
                    style="error"
                )
        else:
            self.console.print(
                f"[red]Error {context}: {str(error)}[/red]",
                style="error"
            )
    
    def print_warning(self, message: str):
        """Print warning message."""
        self.console.print(f"[yellow]{message}[/yellow]", style="warning")
    
    def print_success(self, message: str):
        """Print success message."""
        self.console.print(f"[green]{message}[/green]", style="success")
    
    def print_info(self, message: str):
        """Print info message."""
        self.console.print(f"[cyan]{message}[/cyan]", style="info") 
