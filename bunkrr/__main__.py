"""Main entry point for the bunkrr package."""
import asyncio
import signal
import sys
from pathlib import Path
from typing import NoReturn, Optional, Set, List, AsyncGenerator, Any
from contextlib import asynccontextmanager
import uvloop
import time
import json

from twisted.internet import reactor, selectreactor
from twisted.python import log as twisted_log

from .core.config import DownloadConfig
from .core.decorators import handle_errors, handle_async_errors
from .core.exceptions import BunkrrError, ShutdownError
from .core.logger import setup_logger, log_exception
from .ui.console import ConsoleUI

# Set up main logger with debug level and both console and file output
logger = setup_logger(
    'bunkrr.main',
    level='DEBUG',
    log_dir='logs',
    console=True,
    file=True,
    json=True
)

class BunkrrApp:
    """Main application class for handling downloads and cleanup."""
    
    def __init__(self):
        """Initialize application state and configure signal handlers."""
        self.ui = ConsoleUI()
        self.config = DownloadConfig()
        self._running = True
        self._shutdown_tasks: Set[asyncio.Task] = set()
        self._cleanup_hooks: List[asyncio.Lock] = []
        
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        
        Path('logs').mkdir(exist_ok=True)
        logger.debug(
            "BunkrrApp initialized with config: %s",
            json.dumps(self.config.to_dict(), indent=2)
        )
    
    @handle_errors(target_error=BunkrrError, context='signal_handler')
    def _handle_interrupt(self, signum: int, frame) -> None:
        """Handle interrupt signals and initiate graceful shutdown."""
        if not self._running:
            return
            
        self._running = False
        logger.info(
            "Received interrupt signal %d, cleaning up...",
            signum,
            extra={'signal': signum}
        )
        self.ui.print_warning("\nReceived interrupt signal, cleaning up...")
        
        if asyncio.get_event_loop().is_running():
            asyncio.create_task(self._shutdown())
    
    @asynccontextmanager
    async def cleanup_hook(self) -> AsyncGenerator[None, None]:
        """Provide context for cleanup operations with proper lock management."""
        lock = asyncio.Lock()
        self._cleanup_hooks.append(lock)
        try:
            async with lock:
                yield
        finally:
            self._cleanup_hooks.remove(lock)
            logger.debug(
                "Cleanup hook removed, remaining hooks: %d",
                len(self._cleanup_hooks)
            )
    
    async def _shutdown(self) -> None:
        """Perform graceful shutdown of all resources."""
        start_time = time.time()
        logger.info("Starting graceful shutdown...")
        
        try:
            if self._cleanup_hooks:
                logger.debug(
                    "Waiting for %d cleanup hooks...",
                    len(self._cleanup_hooks)
                )
                await asyncio.gather(*(hook.acquire() for hook in self._cleanup_hooks))
            
            pending = [t for t in self._shutdown_tasks if not t.done()]
            if pending:
                logger.debug(
                    "Cancelling %d pending tasks...",
                    len(pending),
                    extra={'tasks': [str(t) for t in pending]}
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            
            duration = time.time() - start_time
            logger.info(
                "Graceful shutdown completed in %.2f seconds",
                duration,
                extra={'duration': duration}
            )
            
        except Exception as e:
            duration = time.time() - start_time
            log_exception(
                logger,
                e,
                "Failed to perform graceful shutdown",
                duration=duration,
                pending_tasks=len(pending) if 'pending' in locals() else 0
            )
            raise ShutdownError("Failed to perform graceful shutdown") from e
    
    def register_shutdown_task(self, task: asyncio.Task) -> None:
        """Register a task to be cleaned up during shutdown."""
        self._shutdown_tasks.add(task)
        task.add_done_callback(self._shutdown_tasks.discard)
        logger.debug(
            "Registered shutdown task: %s (total: %d)",
            task.get_name(),
            len(self._shutdown_tasks)
        )
    
    @handle_async_errors(target_error=BunkrrError, context='app_run')
    async def run(self) -> int:
        """Run the application and handle downloads."""
        start_time = time.time()
        try:
            from .scrapy import MediaProcessor
            
            self.ui.print_welcome()
            
            urls = self.ui.get_urls()
            if not urls:
                logger.warning("No valid URLs provided")
                self.ui.print_error("No valid URLs provided")
                return 1
                
            download_path = self.ui.get_download_path(default=self.config.downloads_path)
            if not download_path:
                logger.warning("No valid download path provided")
                self.ui.print_error("No valid download path provided")
                return 1
                
            logger.info(
                "Starting URL processing",
                extra={
                    'urls': urls,
                    'download_path': str(download_path),
                    'config': self.config.to_dict()
                }
            )
            
            async with MediaProcessor(self.config) as processor:
                total_success = total_failed = 0
                
                for url in urls:
                    if not self._running:
                        logger.info("Processing interrupted by user")
                        break
                        
                    url_start_time = time.time()
                    logger.debug(
                        "Processing URL: %s",
                        url,
                        extra={'url': url, 'state': 'start'}
                    )
                    
                    try:
                        success, failed = await processor.process_urls([url])
                        total_success += success
                        total_failed += failed
                        
                        url_duration = time.time() - url_start_time
                        logger.info(
                            "URL %s processed in %.2f seconds - Success: %d, Failed: %d",
                            url, url_duration, success, failed,
                            extra={
                                'url': url,
                                'duration': url_duration,
                                'success': success,
                                'failed': failed,
                                'state': 'complete'
                            }
                        )
                        
                    except Exception as e:
                        url_duration = time.time() - url_start_time
                        log_exception(
                            logger,
                            e,
                            "Error processing URL %s",
                            url,
                            duration=url_duration,
                            url=url
                        )
                        total_failed += 1
                    
            duration = time.time() - start_time
            if total_success > 0 or total_failed > 0:
                logger.info(
                    "Download complete",
                    extra={
                        'duration': duration,
                        'total_success': total_success,
                        'total_failed': total_failed,
                        'success_rate': total_success / (total_success + total_failed)
                    }
                )
                self.ui.print_success(
                    f"\nDownload complete: {total_success} successful, "
                    f"{total_failed} failed"
                )
            
            await self._shutdown()
            return 0 if total_failed == 0 else 1
            
        except BunkrrError as e:
            duration = time.time() - start_time
            log_exception(
                logger,
                e,
                "Application error",
                duration=duration
            )
            self.ui.print_error(str(e))
            return 1
            
        except Exception as e:
            duration = time.time() - start_time
            log_exception(
                logger,
                e,
                "Unexpected error",
                duration=duration
            )
            self.ui.print_error(f"An unexpected error occurred: {e}")
            return 1

@handle_errors(target_error=BunkrrError, context='main')
def main() -> NoReturn:
    """Application entry point with platform-specific event loop configuration."""
    start_time = time.time()
    logger.debug("Starting Bunkrr application")
    
    try:
        loop = (
            asyncio.SelectorEventLoop()
            if sys.platform == 'win32'
            else uvloop.new_event_loop()
        )
        
        asyncio.set_event_loop(loop)
        
        # Configure Twisted logging
        log_dir = Path('logs')
        twisted_log_file = log_dir / 'twisted.log'
        twisted_log.startLogging(
            open(twisted_log_file, 'a', encoding='utf-8'),
            setStdout=False
        )
        logger.debug("Twisted logging configured to: %s", twisted_log_file)
        
        app = BunkrrApp()
        exit_code = loop.run_until_complete(app.run())
        
        if reactor.running:
            logger.debug("Stopping Twisted reactor")
            try:
                reactor.stop()
                logger.info("Twisted reactor stopped successfully")
            except Exception as e:
                log_exception(
                    logger,
                    e,
                    "Error stopping reactor",
                    reactor_state='running'
                )
        
        duration = time.time() - start_time
        logger.info(
            "Application finished",
            extra={
                'duration': duration,
                'exit_code': exit_code
            }
        )
        exit(exit_code)
        
    except Exception as e:
        duration = time.time() - start_time
        log_exception(
            logger,
            e,
            "Fatal error in main",
            duration=duration
        )
        raise

if __name__ == '__main__':
    main()
