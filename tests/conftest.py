"""Shared test fixtures and configuration."""
import os
import pytest
import tempfile
import asyncio
from pathlib import Path

# Constants for testing
TEST_TIMEOUT = 30  # seconds
TEST_CHUNK_SIZE = 8192  # bytes
TEST_RATE_LIMIT = 5  # requests per second

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)

@pytest.fixture
def mock_config():
    """Provide mock configuration for testing."""
    return {
        "download": {
            "chunk_size": TEST_CHUNK_SIZE,
            "timeout": TEST_TIMEOUT,
            "max_retries": 3,
            "concurrent_downloads": 2
        },
        "rate_limit": {
            "requests_per_second": TEST_RATE_LIMIT,
            "window_size": 60
        }
    }

@pytest.fixture
def sample_urls():
    """Provide sample URLs for testing."""
    return [
        "https://example.com/file1.mp4",
        "https://example.com/file2.jpg",
        "https://example.com/file3.png"
    ]

@pytest.fixture
def mock_response():
    """Create a mock HTTP response."""
    class MockResponse:
        def __init__(self, status=200, content=b"test content"):
            self.status = status
            self._content = content
            self.headers = {"Content-Length": str(len(content))}

        async def read(self):
            return self._content

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    return MockResponse 
