"""Main entry point for the bunkrr package."""
import asyncio
import signal
from pathlib import Path
from typing import NoReturn, Optional

from .core.config import DownloadConfig
from .core.error_handler import handle_errors, handle_async_errors
from .core.exceptions import BunkrrError
from .core.logger import setup_logger, log_exception
from .scrapy import MediaProcessor
from .ui.console import ConsoleUI
from .utils.input import parse_urls, parse_path

logger = setup_logger('bunkrr.main')

class BunkrrApp:
    """Main application class."""
    
    def __init__(self):
        """Initialize the application."""
        self.ui = ConsoleUI()
        self.config = DownloadConfig()
        self._running = True
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        
    @handle_errors(target_error=BunkrrError, context='signal_handler')
    def _handle_interrupt(self, signum: int, frame) -> None:
        """Handle interrupt signals."""
        if not self._running:
            return
            
        self._running = False
        self.ui.print_warning("\nReceived interrupt signal, cleaning up...")
        
    @handle_async_errors(target_error=BunkrrError, context='app_run')
    async def run(self) -> int:
        """Run the application."""
        try:
            # Print welcome message
            self.ui.print_welcome()
            
            # Get URLs from user
            urls = self.ui.get_urls()
            if not urls:
                self.ui.print_error("No valid URLs provided")
                return 1
                
            # Get download path
            download_path = self.ui.get_download_path()
            if not download_path:
                self.ui.print_error("No valid download path provided")
                return 1
                
            # Process URLs
            async with MediaProcessor(self.config) as processor:
                total_success = total_failed = 0
                
                for url in urls:
                    if not self._running:
                        break
                        
                    success, failed = await processor.process_album(url, download_path)
                    total_success += success
                    total_failed += failed
                    
            # Print final stats
            if total_success > 0 or total_failed > 0:
                self.ui.print_success(
                    f"\nDownload complete: {total_success} successful, "
                    f"{total_failed} failed"
                )
            
            return 0 if total_failed == 0 else 1
            
        except BunkrrError as e:
            self.ui.print_error(str(e))
            return 1
            
        except Exception as e:
            log_exception(logger, e, "running application")
            self.ui.print_error(f"An unexpected error occurred: {e}")
            return 1
            
@handle_errors(target_error=BunkrrError, context='main')
def main() -> NoReturn:
    """Main entry point."""
    app = BunkrrApp()
    exit_code = asyncio.run(app.run())
    exit(exit_code)
    
if __name__ == '__main__':
    main()
