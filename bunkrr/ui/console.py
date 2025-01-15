"""Console UI module."""
from pathlib import Path
from typing import List, Optional, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..core.exceptions import BunkrrError
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.ui')

class ConsoleUI:
    """Console UI class with enhanced error presentation."""
    
    def __init__(self):
        """Initialize the console UI."""
        self.console = Console()
        
    def _format_error(self, error: Exception) -> Text:
        """Format error message with context."""
        if isinstance(error, BunkrrError):
            # Format BunkrrError with additional context
            text = Text()
            text.append("Error: ", style="bold red")
            text.append(str(error), style="red")
            
            if hasattr(error, 'to_dict'):
                error_info = error.to_dict()
                if error_info.get('details'):
                    text.append("\nDetails: ", style="bold red")
                    text.append(error_info['details'], style="red")
                
                # Add context-specific information
                if 'url' in error_info:
                    text.append("\nURL: ", style="bold red")
                    text.append(error_info['url'], style="red")
                if 'status_code' in error_info:
                    text.append("\nStatus Code: ", style="bold red")
                    text.append(str(error_info['status_code']), style="red")
                if 'operation' in error_info:
                    text.append("\nOperation: ", style="bold red")
                    text.append(error_info['operation'], style="red")
            
            return text
        else:
            # Format standard exceptions
            return Text(f"Error: {str(error)}", style="red")

    def print_error(self, message: str, error: Optional[Exception] = None) -> None:
        """Print error message with enhanced formatting."""
        text = Text()
        text.append("❌ ", style="bold red")
        
        if error:
            text.append(self._format_error(error))
        else:
            text.append(message, style="red")
            
        self.console.print(Panel(text, title="Error", border_style="red"))
        logger.error(message, exc_info=bool(error))

    def print_warning(self, message: str) -> None:
        """Print warning message."""
        text = Text()
        text.append("⚠️  ", style="bold yellow")
        text.append(message, style="yellow")
        self.console.print(Panel(text, title="Warning", border_style="yellow"))
        logger.warning(message)

    def print_success(self, message: str) -> None:
        """Print success message."""
        text = Text()
        text.append("✅ ", style="bold green")
        text.append(message, style="green")
        self.console.print(Panel(text, title="Success", border_style="green"))
        logger.info(message)

    def print_info(self, message: str) -> None:
        """Print info message."""
        text = Text()
        text.append("ℹ️  ", style="bold blue")
        text.append(message, style="blue")
        self.console.print(Panel(text, title="Info", border_style="blue"))
        logger.info(message)

    def print_welcome(self) -> None:
        """Print welcome message."""
        welcome_text = Text()
        welcome_text.append("Welcome to ", style="bold blue")
        welcome_text.append("Bunkrr", style="bold cyan")
        welcome_text.append("!", style="bold blue")
        welcome_text.append("\nA high-performance media downloader", style="blue")
        
        self.console.print(Panel(welcome_text, title="Bunkrr", border_style="blue"))
        logger.info("Application started")

    def get_urls(self) -> List[str]:
        """Get URLs from user input."""
        self.print_info("Enter URLs (one per line, empty line to finish):")
        urls = []
        while True:
            try:
                url = input().strip()
                if not url:
                    break
                urls.append(url)
            except EOFError:
                break
            except KeyboardInterrupt:
                self.print_warning("\nInput cancelled")
                return []
                
        return urls

    def get_download_path(self, default: Optional[Path] = None) -> Optional[Path]:
        """Get download path from user input."""
        if default:
            self.print_info(f"Enter download path (default: {default}):")
        else:
            self.print_info("Enter download path:")
            
        try:
            path_str = input().strip()
            if not path_str and default:
                return default
            return Path(path_str).expanduser().resolve()
        except (EOFError, KeyboardInterrupt):
            self.print_warning("\nInput cancelled")
            return None
        except Exception as e:
            self.print_error("Invalid path", error=e)
            return None

    def create_progress_bar(
        self,
        total: int,
        description: str = "Downloading"
    ) -> Progress:
        """Create a progress bar."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            console=self.console
        ) 
