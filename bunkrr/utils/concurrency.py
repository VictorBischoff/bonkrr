"""Concurrency utilities for the bunkrr package."""
import asyncio
import functools
import signal
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Optional, Set, TypeVar

from ..core.exceptions import BunkrrError
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.concurrency')

T = TypeVar('T')

class CancellationToken:
    """Token for managing cancellation of async operations."""
    
    def __init__(self):
        """Initialize cancellation token."""
        self._cancelled = False
        self._callbacks: Set[Callable[[], None]] = set()
    
    def cancel(self) -> None:
        """Cancel the operation."""
        if not self._cancelled:
            self._cancelled = True
            for callback in self._callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error("Cancellation callback error: %s", str(e))
    
    @property
    def is_cancelled(self) -> bool:
        """Check if operation is cancelled."""
        return self._cancelled
    
    def add_callback(self, callback: Callable[[], None]) -> None:
        """Add cancellation callback."""
        if not self._cancelled:
            self._callbacks.add(callback)
    
    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove cancellation callback."""
        self._callbacks.discard(callback)

class AsyncPool:
    """Pool for managing concurrent async tasks."""
    
    def __init__(
        self,
        max_workers: int,
        cancellation_token: Optional[CancellationToken] = None
    ):
        """Initialize async pool."""
        self.max_workers = max_workers
        self.cancellation_token = cancellation_token or CancellationToken()
        self._semaphore = asyncio.Semaphore(max_workers)
        self._tasks: Set[asyncio.Task] = set()
    
    async def _run_task(
        self,
        coro: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """Run task with semaphore and error handling."""
        async with self._semaphore:
            if self.cancellation_token.is_cancelled:
                raise asyncio.CancelledError()
                
            try:
                return await coro(*args, **kwargs)
            except Exception as e:
                logger.error("Task error: %s", str(e))
                raise
    
    def create_task(
        self,
        coro: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> asyncio.Task[T]:
        """Create and track a new task."""
        if self.cancellation_token.is_cancelled:
            raise asyncio.CancelledError()
            
        task = asyncio.create_task(
            self._run_task(coro, *args, **kwargs)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task
    
    async def join(self) -> None:
        """Wait for all tasks to complete."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
    
    def cancel_all(self) -> None:
        """Cancel all running tasks."""
        for task in self._tasks:
            task.cancel()

@asynccontextmanager
async def async_pool(
    max_workers: int,
    cancellation_token: Optional[CancellationToken] = None
) -> AsyncGenerator[AsyncPool, None]:
    """Context manager for AsyncPool."""
    pool = AsyncPool(max_workers, cancellation_token)
    try:
        yield pool
    finally:
        pool.cancel_all()
        await pool.join()

class ThreadPool:
    """Thread pool for CPU-bound tasks."""
    
    def __init__(
        self,
        max_workers: Optional[int] = None,
        thread_name_prefix: str = 'BunkrrWorker'
    ):
        """Initialize thread pool."""
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix
        )
    
    async def run(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any
    ) -> T:
        """Run function in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.executor,
            functools.partial(func, *args, **kwargs)
        )
    
    def shutdown(self, wait: bool = True) -> None:
        """Shutdown thread pool."""
        self.executor.shutdown(wait=wait)

@asynccontextmanager
async def thread_pool(
    max_workers: Optional[int] = None,
    thread_name_prefix: str = 'BunkrrWorker'
) -> AsyncGenerator[ThreadPool, None]:
    """Context manager for ThreadPool."""
    pool = ThreadPool(max_workers, thread_name_prefix)
    try:
        yield pool
    finally:
        pool.shutdown()

def setup_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    cancellation_token: CancellationToken
) -> None:
    """Setup signal handlers for graceful shutdown."""
    def signal_handler():
        logger.info("Received shutdown signal")
        cancellation_token.cancel()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            signal_handler
        )

async def wait_for_with_token(
    coro: Callable[..., T],
    timeout: Optional[float],
    cancellation_token: CancellationToken,
    *args: Any,
    **kwargs: Any
) -> T:
    """Wait for coroutine with timeout and cancellation support."""
    if cancellation_token.is_cancelled:
        raise asyncio.CancelledError()
        
    try:
        return await asyncio.wait_for(
            coro(*args, **kwargs),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise BunkrrError(
            "Operation timed out",
            f"Timeout after {timeout} seconds"
        )
    except asyncio.CancelledError:
        if cancellation_token.is_cancelled:
            raise BunkrrError("Operation cancelled")
        raise 
