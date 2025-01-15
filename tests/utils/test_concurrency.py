"""Test concurrency utilities."""
import asyncio
import pytest
import signal
from unittest.mock import Mock

from bunkrr.core.exceptions import BunkrrError
from bunkrr.utils.concurrency import (
    CancellationToken,
    AsyncPool,
    ThreadPool,
    async_pool,
    thread_pool,
    setup_signal_handlers,
    wait_for_with_token
)

@pytest.mark.asyncio
async def test_cancellation_token():
    """Test cancellation token functionality."""
    token = CancellationToken()
    callback = Mock()
    
    # Test initial state
    assert not token.is_cancelled
    
    # Test callback registration
    token.add_callback(callback)
    token.cancel()
    callback.assert_called_once()
    
    # Test callback removal
    token.remove_callback(callback)
    callback.reset_mock()
    token.cancel()  # Second cancel should not trigger callback
    callback.assert_not_called()

@pytest.mark.asyncio
async def test_async_pool():
    """Test async pool functionality."""
    async def task(x):
        await asyncio.sleep(0.1)
        return x * 2
    
    pool = AsyncPool(max_workers=2)
    
    # Test task creation and execution
    tasks = [
        pool.create_task(task, i)
        for i in range(3)
    ]
    
    results = await asyncio.gather(*tasks)
    assert results == [0, 2, 4]
    
    # Test cancellation
    pool.cancel_all()
    await pool.join()

@pytest.mark.asyncio
async def test_async_pool_context():
    """Test async pool context manager."""
    async def task(x):
        await asyncio.sleep(0.1)
        return x * 2
    
    async with async_pool(max_workers=2) as pool:
        tasks = [
            pool.create_task(task, i)
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)
        assert results == [0, 2, 4]

@pytest.mark.asyncio
async def test_thread_pool():
    """Test thread pool functionality."""
    def cpu_bound(x):
        return x * 2
    
    async with thread_pool(max_workers=2) as pool:
        results = await asyncio.gather(*[
            pool.run(cpu_bound, i)
            for i in range(3)
        ])
        assert results == [0, 2, 4]

@pytest.mark.asyncio
async def test_wait_for_with_token():
    """Test wait_for with cancellation token."""
    async def slow_task():
        await asyncio.sleep(1)
        return "done"
    
    token = CancellationToken()
    
    # Test successful completion
    result = await wait_for_with_token(
        slow_task,
        timeout=2,
        cancellation_token=token
    )
    assert result == "done"
    
    # Test timeout
    with pytest.raises(BunkrrError) as exc_info:
        await wait_for_with_token(
            slow_task,
            timeout=0.1,
            cancellation_token=token
        )
    assert "timeout" in str(exc_info.value).lower()
    
    # Test cancellation
    token.cancel()
    with pytest.raises(BunkrrError) as exc_info:
        await wait_for_with_token(
            slow_task,
            timeout=1,
            cancellation_token=token
        )
    assert "cancelled" in str(exc_info.value).lower()

def test_setup_signal_handlers():
    """Test signal handler setup."""
    loop = asyncio.new_event_loop()
    token = CancellationToken()
    
    try:
        setup_signal_handlers(loop, token)
        
        # Verify handlers are set
        assert loop.get_exception_handler() is not None
        
        # Test SIGINT handling
        loop.call_soon_threadsafe(
            lambda: signal.raise_signal(signal.SIGINT)
        )
        
        # Run loop briefly to process signal
        loop.run_until_complete(asyncio.sleep(0.1))
        
        assert token.is_cancelled
        
    finally:
        loop.close() 
