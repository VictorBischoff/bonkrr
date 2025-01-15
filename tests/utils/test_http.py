"""Test HTTP utilities."""
import pytest
import aiohttp
from aiohttp import ClientResponse, ClientSession
from unittest.mock import Mock, patch

from bunkrr.core.exceptions import DownloadError
from bunkrr.utils.http import (
    HTTPClient,
    normalize_url,
    join_urls,
    DEFAULT_HEADERS
)

@pytest.mark.asyncio
async def test_http_client():
    """Test HTTP client functionality."""
    async with HTTPClient() as client:
        assert isinstance(client.session, ClientSession)
        assert client.headers == DEFAULT_HEADERS

@pytest.mark.asyncio
async def test_http_client_custom_config():
    """Test HTTP client with custom configuration."""
    custom_headers = {"User-Agent": "Test/1.0"}
    custom_timeout = 60
    custom_retries = 5
    custom_retry_codes = {500, 502}
    
    async with HTTPClient(
        timeout=custom_timeout,
        headers=custom_headers,
        max_retries=custom_retries,
        retry_codes=custom_retry_codes
    ) as client:
        assert client.max_retries == custom_retries
        assert client.retry_codes == custom_retry_codes
        assert client.headers["User-Agent"] == "Test/1.0"
        assert client.timeout.total == custom_timeout

@pytest.mark.asyncio
async def test_http_client_get():
    """Test HTTP client GET request."""
    async with HTTPClient() as client:
        # Mock successful response
        mock_response = Mock(spec=ClientResponse)
        mock_response.status = 200
        
        with patch.object(client.session, 'get', return_value=mock_response):
            response = await client.get("https://example.com")
            assert response.status == 200

@pytest.mark.asyncio
async def test_http_client_retry():
    """Test HTTP client retry behavior."""
    async with HTTPClient(max_retries=2) as client:
        # Mock responses for retry
        responses = [
            Mock(spec=ClientResponse, status=503),  # First attempt fails
            Mock(spec=ClientResponse, status=200)   # Second attempt succeeds
        ]
        
        with patch.object(
            client.session,
            'get',
            side_effect=responses
        ):
            response = await client.get("https://example.com")
            assert response.status == 200

@pytest.mark.asyncio
async def test_http_client_rate_limit():
    """Test HTTP client rate limit handling."""
    async with HTTPClient(max_retries=1) as client:
        # Mock rate limited response
        mock_response = Mock(spec=ClientResponse)
        mock_response.status = 429
        mock_response.headers = {"Retry-After": "1"}
        
        with patch.object(
            client.session,
            'get',
            side_effect=[mock_response, Mock(spec=ClientResponse, status=200)]
        ):
            response = await client.get("https://example.com")
            assert response.status == 200

@pytest.mark.asyncio
async def test_http_client_error():
    """Test HTTP client error handling."""
    async with HTTPClient(max_retries=1) as client:
        # Mock error response
        mock_response = Mock(spec=ClientResponse)
        mock_response.status = 500
        mock_response.text = Mock(return_value="Server Error")
        
        with patch.object(client.session, 'get', return_value=mock_response):
            with pytest.raises(DownloadError) as exc_info:
                await client.get("https://example.com")
            assert "500" in str(exc_info.value)

@pytest.mark.asyncio
async def test_http_client_network_error():
    """Test HTTP client network error handling."""
    async with HTTPClient(max_retries=1) as client:
        with patch.object(
            client.session,
            'get',
            side_effect=aiohttp.ClientError("Network error")
        ):
            with pytest.raises(DownloadError) as exc_info:
                await client.get("https://example.com")
            assert "Network error" in str(exc_info.value)

def test_normalize_url():
    """Test URL normalization."""
    test_cases = [
        # Basic normalization
        ("HTTP://Example.Com", "http://example.com"),
        # Remove fragments
        ("http://example.com#fragment", "http://example.com"),
        # Preserve query parameters
        ("http://example.com?q=test", "http://example.com?q=test"),
        # Handle empty URL
        ("", ""),
        # Handle invalid URL
        ("not_a_url", "not_a_url"),
        # Handle multiple fragments
        ("http://example.com#one#two", "http://example.com"),
        # Handle special characters
        ("http://example.com/path%20with%20spaces", "http://example.com/path%20with%20spaces")
    ]
    
    for input_url, expected in test_cases:
        assert normalize_url(input_url) == expected

def test_join_urls():
    """Test URL joining."""
    test_cases = [
        # Basic joining
        ("http://example.com", "path", "http://example.com/path"),
        # Handle trailing slash
        ("http://example.com/", "path", "http://example.com/path"),
        # Handle absolute URLs
        ("http://example.com", "http://other.com", "http://other.com"),
        # Handle empty path
        ("http://example.com", "", "http://example.com"),
        # Handle query parameters
        ("http://example.com", "path?q=test", "http://example.com/path?q=test"),
        # Handle relative paths
        ("http://example.com/base", "../path", "http://example.com/path"),
        # Handle special characters
        ("http://example.com", "path with spaces", "http://example.com/path%20with%20spaces")
    ]
    
    for base, url, expected in test_cases:
        assert join_urls(base, url) == expected 
