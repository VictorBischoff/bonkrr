"""Console UI utilities."""
from typing import Optional, List
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..core.error_handler import ErrorHandler
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.ui')

class ConsoleUI:
    """Console user interface handler."""
    
    def __init__(self):
        """Initialize console UI."""
        self.console = Console()
    
    def print_error(self, message: str, error: Optional[Exception] = None) -> None:
        """Print error message with enhanced formatting."""
        text = Text()
        text.append("❌ ", style="bold red")
        
        if error:
            text.append(ErrorHandler.format_error(error))
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
        text = Text()
        text.append("🚀 ", style="bold cyan")
        text.append("Welcome to Bunkrr - A fast and efficient downloader for Bunkr.site", style="cyan")
        text.append("\n\n")
        text.append("Version: ", style="dim")
        text.append("0.1.0", style="cyan")
        text.append("\n")
        text.append("Author: ", style="dim")
        text.append("Victor", style="cyan")
        text.append("\n\n")
        text.append("Type URLs to download or press Ctrl+C to exit", style="italic")
        
        self.console.print(Panel(text, title="Bunkrr", border_style="cyan"))
        logger.info("Welcome message displayed")
    
    def get_urls(self) -> List[str]:
        """Get URLs from user input.
        
        Returns:
            List of URLs to process
        """
        urls = []
        
        try:
            self.console.print("\nEnter URLs (one per line, empty line to finish):", style="cyan")
            while True:
                try:
                    url = input().strip()
                    if not url:
                        break
                        
                    # Basic URL validation
                    if not url.startswith(('http://', 'https://')):
                        self.print_warning(f"Invalid URL format: {url}")
                        continue
                        
                    # Additional validation for bunkr URLs
                    if not any(domain in url for domain in [
                        'bunkr.site', 'bunkr.ru', 'bunkr.ph', 'bunkr.is', 'bunkr.to', 'bunkr.fi'
                    ]):
                        self.print_warning(f"Not a valid Bunkr URL: {url}")
                        continue
                        
                    urls.append(url)
                    logger.debug("Added URL: %s", url)
                except UnicodeDecodeError:
                    self.print_error("Invalid input encoding. Please enter valid URLs.")
                    continue
            
            if not urls:
                self.print_warning("No valid URLs provided")
            else:
                self.print_info(f"Added {len(urls)} valid URLs for processing")
            
            return urls
            
        except (KeyboardInterrupt, EOFError):
            logger.info("URL input interrupted by user")
            return urls
        except Exception as e:
            logger.error("Error getting URLs: %s", str(e), exc_info=True)
            self.print_error("Failed to get URLs", e)
            return urls
    
    def get_download_path(self, default: Optional[Path] = None) -> Optional[Path]:
        """Get download path from user input.
        
        Args:
            default: Default download path
            
        Returns:
            Selected download path or None if invalid
        """
        try:
            if default:
                self.console.print(
                    f"\nDownload path [default: {default}]: ",
                    style="cyan",
                    end=""
                )
                path_str = input().strip()
                if not path_str:
                    path = default
                else:
                    path = Path(path_str).expanduser().resolve()
            else:
                self.console.print("\nDownload path: ", style="cyan", end="")
                path_str = input().strip()
                if not path_str:
                    self.print_warning("No download path provided")
                    return None
                path = Path(path_str).expanduser().resolve()
            
            # Validate path
            if path.exists() and not path.is_dir():
                self.print_error(f"Path exists but is not a directory: {path}")
                return None
                
            # Check write permissions
            try:
                path.mkdir(parents=True, exist_ok=True)
                test_file = path / '.write_test'
                test_file.touch()
                test_file.unlink()
            except (OSError, PermissionError) as e:
                self.print_error(f"Cannot write to directory: {path}", e)
                return None
                
            logger.debug("Using download path: %s", path)
            return path
            
        except (KeyboardInterrupt, EOFError):
            logger.info("Download path input interrupted by user")
            return None
        except Exception as e:
            logger.error("Error getting download path: %s", str(e), exc_info=True)
            self.print_error("Failed to get download path", e)
            return None
