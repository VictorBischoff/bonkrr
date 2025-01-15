"""Console UI utilities."""
from typing import Optional
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
