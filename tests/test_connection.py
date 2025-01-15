"""Tests for connection pooling and timeout management."""
import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
from aiohttp import (
    ClientSession,
    ClientTimeout,
    ClientResponse,
    TraceConfig,
    client_exceptions,
    ClientConnectionError,
    ServerDisconnectedError
)

from bunkrr.data_processing import (
    MediaProcessor,
    MAX_CONNECTIONS_PER_HOST,
    DNS_CACHE_TTL,
    KEEPALIVE_TIMEOUT,
    CONNECT_TIMEOUT,
    READ_TIMEOUT,
    TOTAL_TIMEOUT
)
from bunkrr.config import DownloadConfig

@pytest.fixture
def config():
    """Create a test configuration."""
    return DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )

@pytest.mark.asyncio
async def test_connection_pool_config():
    """Test that connection pool is configured correctly."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    
    # Verify connector settings
    assert processor._connector.limit == config.max_concurrent_downloads * 2
    assert processor._connector.limit_per_host == MAX_CONNECTIONS_PER_HOST
    assert processor._connector.use_dns_cache  # DNS caching enabled
    assert processor._connector._keepalive_timeout == KEEPALIVE_TIMEOUT
    assert not processor._connector.force_close
    assert processor._connector._cleanup_closed  # Internal attribute name

@pytest.mark.asyncio
async def test_session_timeout_config():
    """Test that session timeouts are configured correctly."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    async with MediaProcessor(config) as processor:
        assert processor._session.timeout.total == TOTAL_TIMEOUT
        assert processor._session.timeout.connect == CONNECT_TIMEOUT
        assert processor._session.timeout.sock_read == READ_TIMEOUT

@pytest.mark.asyncio
async def test_connection_monitoring():
    """Test that connection monitoring callbacks are working."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    
    # Create mock session and context
    session = Mock()
    trace_config_ctx = Mock()
    
    # Test monitoring callbacks
    await processor._on_connection_queued_start(session, trace_config_ctx, {})
    await processor._on_connection_queued_end(session, trace_config_ctx, {})
    await processor._on_connection_create_start(session, trace_config_ctx, {})
    await processor._on_connection_create_end(session, trace_config_ctx, {})

@pytest.mark.asyncio
async def test_request_retry_behavior():
    """Test that requests are retried with exponential backoff."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    processor._session = AsyncMock(spec=ClientSession)
    
    # Mock a connection error that can be awaited
    async def raise_error(*args, **kwargs):
        raise client_exceptions.ServerTimeoutError()
    processor._session.request.side_effect = raise_error
    
    with pytest.raises(client_exceptions.ServerTimeoutError):
        await processor._make_request('GET', 'http://test.com')
    
    # Should have retried max_retries times
    assert processor._session.request.call_count == config.max_retries

@pytest.mark.asyncio
async def test_keepalive_headers():
    """Test that keep-alive headers are properly set."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    processor._session = AsyncMock(spec=ClientSession)
    
    # Mock a successful response that can be awaited
    mock_response = AsyncMock(spec=ClientResponse)
    async def return_response(*args, **kwargs):
        return mock_response
    processor._session.request.side_effect = return_response
    
    await processor._make_request('GET', 'http://test.com')
    
    # Verify headers
    call_kwargs = processor._session.request.call_args[1]
    headers = call_kwargs['headers']
    assert headers['Connection'] == 'keep-alive'
    assert headers['Keep-Alive'] == f'timeout={KEEPALIVE_TIMEOUT}'
    assert headers['Accept-Encoding'] == 'gzip, deflate'

@pytest.mark.asyncio
async def test_graceful_shutdown():
    """Test that session is closed gracefully."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    processor._session = AsyncMock(spec=ClientSession)
    processor._connector = AsyncMock()
    
    # Configure async close methods
    async def close_session():
        return None
    processor._session.close.side_effect = close_session
    processor._connector.close.side_effect = close_session
    
    # Test normal shutdown
    await processor.__aexit__(None, None, None)
    processor._session.close.assert_awaited_once()
    processor._connector.close.assert_awaited_once()
    
    # Test timeout during shutdown
    async def timeout_close():
        raise asyncio.TimeoutError()
    processor._session.close.side_effect = timeout_close
    await processor.__aexit__(None, None, None)
    # Should still close connector even if session close times out
    assert processor._connector.close.await_count == 2 

@pytest.mark.asyncio
async def test_connection_pool_exhaustion():
    """Test behavior when connection pool is exhausted."""
    config = DownloadConfig(
        max_concurrent_downloads=2,  # Small pool for testing
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )

    processor = MediaProcessor(config)

    # Mock connector to simulate pool exhaustion
    class MockConnector:
        def __init__(self):
            self.limit = config.max_concurrent_downloads * 2
            self.limit_per_host = config.max_concurrent_downloads
            self.use_dns_cache = True
            self._keepalive_timeout = KEEPALIVE_TIMEOUT
            self.force_close = False
            self._cleanup_closed = True
            self._active_connections = 0
            self._lock = asyncio.Lock()
            self.pool_exhaustion_count = 0  # Track pool exhaustion errors

        async def acquire(self):
            async with self._lock:
                if self._active_connections >= self.limit_per_host:
                    self.pool_exhaustion_count += 1
                    raise client_exceptions.ClientConnectionError("Pool exhausted")
                self._active_connections += 1
                await asyncio.sleep(0.1)  # Ensure some connections overlap

        async def release(self):
            async with self._lock:
                if self._active_connections > 0:
                    self._active_connections -= 1

        async def close(self):
            self._active_connections = 0

    connector = MockConnector()
    processor._connector = connector
    processor._session = AsyncMock(spec=ClientSession)

    # Mock session to use our connector
    async def mock_request(*args, **kwargs):
        try:
            await connector.acquire()
            await asyncio.sleep(0.2)  # Hold the connection longer
            return AsyncMock(spec=ClientResponse)
        finally:
            await connector.release()

    processor._session.request.side_effect = mock_request

    # Make concurrent requests exceeding pool size
    tasks = [
        processor._make_request('GET', f'http://test.com/{i}')
        for i in range(5)  # More than max_concurrent_downloads
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Verify that pool exhaustion occurred, even if requests eventually succeeded through retries
    assert connector.pool_exhaustion_count > 0, \
        f"Expected pool exhaustion to occur, but got {connector.pool_exhaustion_count} exhaustion errors"

@pytest.mark.asyncio
async def test_connection_retry_backoff():
    """Test exponential backoff for connection retries."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    processor._session = AsyncMock(spec=ClientSession)
    
    retry_delays = []
    retry_count = 0
    
    # Mock sleep to capture delays without recursion
    original_sleep = asyncio.sleep
    async def mock_sleep(delay):
        retry_delays.append(delay)
        await original_sleep(0)  # Use real sleep with minimal delay
    
    # Simulate connection errors with retry tracking
    async def fail_with_error(*args, **kwargs):
        nonlocal retry_count
        retry_count += 1
        raise client_exceptions.ServerTimeoutError()
    
    processor._session.request.side_effect = fail_with_error
    
    with patch('asyncio.sleep', mock_sleep):
        with pytest.raises(client_exceptions.ServerTimeoutError):
            await processor._make_request('GET', 'http://test.com')
    
    # Verify exponential backoff
    assert retry_count == config.max_retries, \
        f"Expected {config.max_retries} retries, got {retry_count}"
    assert len(retry_delays) == config.max_retries - 1, \
        f"Expected {config.max_retries - 1} delays, got {len(retry_delays)}"
    if len(retry_delays) >= 2:
        assert retry_delays[1] > retry_delays[0], "Delays should increase"

@pytest.mark.asyncio
async def test_connection_error_handling():
    """Test handling of various connection errors."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    processor._session = AsyncMock(spec=ClientSession)
    
    # Test different error types
    errors = [
        ClientConnectionError(),
        ServerDisconnectedError(),
        asyncio.TimeoutError(),
        client_exceptions.ClientOSError(),
        client_exceptions.ClientPayloadError()
    ]
    
    original_sleep = asyncio.sleep
    
    for error in errors:
        retry_count = 0
        retry_delays = []
        
        # Mock sleep to avoid actual delays without recursion
        async def mock_sleep(delay):
            retry_delays.append(delay)
            await original_sleep(0)
        
        async def raise_error(*args, **kwargs):
            nonlocal retry_count
            retry_count += 1
            raise error
        
        processor._session.request.side_effect = raise_error
        processor._session.request.reset_mock()
        
        with patch('asyncio.sleep', mock_sleep):
            with pytest.raises(type(error)):
                await processor._make_request('GET', 'http://test.com')
        
        # Verify retry behavior
        assert retry_count == config.max_retries, \
            f"Expected {config.max_retries} retries for {error.__class__.__name__}, got {retry_count}"
        assert len(retry_delays) == config.max_retries - 1, \
            f"Expected {config.max_retries - 1} delays for {error.__class__.__name__}, got {len(retry_delays)}"
        if len(retry_delays) >= 2:
            assert retry_delays[1] > retry_delays[0], \
                f"Delays should increase for {error.__class__.__name__}"

@pytest.mark.asyncio
async def test_connection_cleanup_on_error():
    """Test proper cleanup of connections on errors."""
    config = DownloadConfig(
        max_concurrent_downloads=4,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    processor._session = AsyncMock(spec=ClientSession)
    processor._connector = AsyncMock()
    
    # Simulate error during session use
    processor._session.request.side_effect = ServerDisconnectedError()
    
    # Try a request that will fail
    with pytest.raises(ServerDisconnectedError):
        await processor._make_request('GET', 'http://test.com')
    
    # Verify cleanup
    await processor.__aexit__(None, None, None)
    processor._session.close.assert_awaited_once()
    processor._connector.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_concurrent_connection_limits():
    """Test enforcement of concurrent connection limits."""
    config = DownloadConfig(
        max_concurrent_downloads=2,
        rate_limit=10,
        rate_window=60,
        retry_delay=1,
        max_retries=3,
        min_file_size=1024,
        download_timeout=300
    )
    
    processor = MediaProcessor(config)
    
    # Mock connector to enforce limits
    class MockConnector:
        def __init__(self):
            self.limit = config.max_concurrent_downloads * 2
            self.limit_per_host = config.max_concurrent_downloads
            self._active_connections = 0
            self._lock = asyncio.Lock()
            
        async def acquire(self):
            async with self._lock:
                if self._active_connections >= self.limit_per_host:
                    raise client_exceptions.ClientConnectionError("Too many connections")
                self._active_connections += 1
                
        async def release(self):
            async with self._lock:
                self._active_connections = max(0, self._active_connections - 1)
    
    connector = MockConnector()
    processor._connector = connector
    processor._session = AsyncMock(spec=ClientSession)
    
    async def simulated_request(*args, **kwargs):
        await connector.acquire()
        try:
            await asyncio.sleep(0.1)  # Simulate work
            return AsyncMock(spec=ClientResponse)
        finally:
            await connector.release()
    
    processor._session.request.side_effect = simulated_request
    
    # Make several concurrent requests
    tasks = [
        processor._make_request('GET', f'http://test.com/{i}')
        for i in range(5)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = sum(1 for r in results if not isinstance(r, Exception))
    assert successful <= config.max_concurrent_downloads
