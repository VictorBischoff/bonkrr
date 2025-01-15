"""Main entry point for the bunkrr package."""
import asyncio
import signal
import sys
from pathlib import Path
from typing import NoReturn, Optional, Set, List
from contextlib import asynccontextmanager

# Import reactor but don't install it (processor.py will handle installation)
from twisted.internet import selectreactor

# Only import what we need initially
from .core.config import DownloadConfig
from .core.error_handler import handle_errors, handle_async_errors
from .core.exceptions import BunkrrError, ShutdownError
from .core.logger import setup_logger, log_exception
from .ui.console import ConsoleUI

logger = setup_logger('bunkrr.main')

class BunkrrApp:
    """Main application class."""
    
    def __init__(self):
        """Initialize the application."""
        self.ui = ConsoleUI()
        self.config = DownloadConfig()
        self._running = True
        self._shutdown_tasks: Set[asyncio.Task] = set()
        self._cleanup_hooks: List[asyncio.Lock] = []
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        
        # Create logs directory
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        logger.debug("BunkrrApp initialized")

    @handle_errors(target_error=BunkrrError, context='signal_handler')
    def _handle_interrupt(self, signum: int, frame) -> None:
        """Handle interrupt signals."""
        if not self._running:
            return
            
        self._running = False
        logger.info("Received interrupt signal %d, cleaning up...", signum)
        self.ui.print_warning("\nReceived interrupt signal, cleaning up...")
        
        # Schedule shutdown in the event loop
        if asyncio.get_event_loop().is_running():
            asyncio.create_task(self._shutdown())

    @asynccontextmanager
    async def cleanup_hook(self) -> None:
        """Context manager for cleanup operations.
        
        Usage:
            async with app.cleanup_hook():
                # Your code here
                # Will be cleaned up properly on shutdown
        """
        lock = asyncio.Lock()
        self._cleanup_hooks.append(lock)
        try:
            async with lock:
                yield
        finally:
            self._cleanup_hooks.remove(lock)

    async def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Starting graceful shutdown...")
        
        try:
            # Wait for cleanup hooks to complete
            if self._cleanup_hooks:
                logger.debug("Waiting for %d cleanup hooks...", len(self._cleanup_hooks))
                await asyncio.gather(*(hook.acquire() for hook in self._cleanup_hooks))
            
            # Cancel pending tasks
            pending = [t for t in self._shutdown_tasks if not t.done()]
            if pending:
                logger.debug("Cancelling %d pending tasks...", len(pending))
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            
            logger.info("Graceful shutdown completed")
            
        except Exception as e:
            logger.error("Error during shutdown: %s", str(e))
            raise ShutdownError("Failed to perform graceful shutdown") from e

    def register_shutdown_task(self, task: asyncio.Task) -> None:
        """Register a task to be cleaned up during shutdown."""
        self._shutdown_tasks.add(task)
        task.add_done_callback(self._shutdown_tasks.discard)

    @handle_async_errors(target_error=BunkrrError, context='app_run')
    async def run(self) -> int:
        """Run the application.
        
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        try:
            # Import MediaProcessor here to avoid early reactor import
            from .scrapy import MediaProcessor
            
            # Print welcome message
            self.ui.print_welcome()
            
            # Get URLs from user
            urls = self.ui.get_urls()
            if not urls:
                self.ui.print_error("No valid URLs provided")
                return 1
                
            # Get download path
            download_path = self.ui.get_download_path(default=self.config.downloads_path)
            if not download_path:
                self.ui.print_error("No valid download path provided")
                return 1
                
            logger.debug("Starting URL processing with download path: %s", download_path)
            
            # Process URLs
            async with MediaProcessor(self.config) as processor:
                total_success = total_failed = 0
                
                for url in urls:
                    if not self._running:
                        logger.info("Processing interrupted by user")
                        break
                        
                    logger.debug("Processing URL: %s", url)
                    success, failed = await processor.process_urls([url], download_path)
                    total_success += success
                    total_failed += failed
                    logger.debug(
                        "URL %s processed. Success: %d, Failed: %d",
                        url, success, failed
                    )
                    
            # Print final stats
            if total_success > 0 or total_failed > 0:
                logger.info(
                    "Download complete. Total success: %d, Total failed: %d",
                    total_success, total_failed
                )
                self.ui.print_success(
                    f"\nDownload complete: {total_success} successful, "
                    f"{total_failed} failed"
                )
            
            # Perform graceful shutdown
            await self._shutdown()
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
    logger.debug("Starting Bunkrr application")
    
    try:
        # Configure event loop based on platform
        if sys.platform == 'win32':
            # Windows requires SelectorEventLoop
            loop = asyncio.SelectorEventLoop()
        else:
            # Use uvloop on Unix platforms
            import uvloop
            loop = uvloop.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
        # Configure Twisted logging
        from twisted.python import log as twisted_log
        twisted_log.startLogging(
            open('logs/twisted.log', 'a'),
            setStdout=False
        )
        
        # Create and run application
        app = BunkrrApp()
        exit_code = loop.run_until_complete(app.run())
        
        # Get reactor from selectreactor
        if selectreactor._the_reactor and selectreactor._the_reactor.running:
            logger.debug("Stopping Twisted reactor")
            try:
                selectreactor._the_reactor.stop()
                logger.info("Twisted reactor stopped successfully")
            except Exception as e:
                logger.error("Error stopping reactor: %s", str(e), exc_info=True)
        
        logger.debug("Application finished with exit code: %d", exit_code)
        exit(exit_code)
        
    except Exception as e:
        logger.error("Fatal error in main: %s", str(e), exc_info=True)
        raise

if __name__ == '__main__':
    main()
