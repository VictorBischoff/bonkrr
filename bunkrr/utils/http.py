"""HTTP utilities for the bunkrr package."""
from typing import Dict, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp import ClientResponse, ClientSession, ClientTimeout
from yarl import URL

from ..core.exceptions import DownloadError
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.http')

# Default timeout settings
DEFAULT_TIMEOUT = ClientTimeout(total=30, connect=10)

# Common headers
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache'
}

class HTTPClient:
    """HTTP client with session management and retries."""
    
    def __init__(
        self,
        timeout: Optional[Union[float, ClientTimeout]] = None,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        retry_codes: Optional[set[int]] = None
    ):
        """Initialize HTTP client."""
        self.timeout = timeout or DEFAULT_TIMEOUT
        if isinstance(self.timeout, (int, float)):
            self.timeout = ClientTimeout(total=float(self.timeout))
            
        self.headers = {**DEFAULT_HEADERS, **(headers or {})}
        self.max_retries = max_retries
        self.retry_codes = retry_codes or {408, 429, 500, 502, 503, 504}
        self._session: Optional[ClientSession] = None
    
    async def __aenter__(self) -> 'HTTPClient':
        """Create session on enter."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers=self.headers
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close session on exit."""
        if self._session:
            await self._session.close()
            self._session = None
    
    @property
    def session(self) -> ClientSession:
        """Get current session or raise error."""
        if not self._session:
            raise RuntimeError("Session not initialized. Use async with context.")
        return self._session
    
    async def _handle_response(
        self,
        response: ClientResponse,
        url: str,
        retry_count: int
    ) -> Tuple[bool, Optional[str]]:
        """Handle response and determine if retry needed."""
        status = response.status
        
        # Success
        if 200 <= status < 300:
            return False, None
            
        # Rate limit response
        if status == 429:
            retry_after = response.headers.get('Retry-After')
            return True, f"Rate limited (retry after: {retry_after})"
            
        # Retryable error
        if status in self.retry_codes and retry_count < self.max_retries:
            return True, f"Retryable error {status}"
            
        # Non-retryable error
        error_msg = f"HTTP {status}"
        try:
            error_msg = f"{error_msg} - {await response.text()}"
        except:
            pass
            
        raise DownloadError(
            f"Failed to download {url}",
            f"Status: {status}, Error: {error_msg}"
        )
    
    async def get(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        allow_redirects: bool = True
    ) -> ClientResponse:
        """Send GET request with retries."""
        merged_headers = {**self.headers, **(headers or {})}
        
        for retry in range(self.max_retries + 1):
            try:
                response = await self.session.get(
                    url,
                    params=params,
                    headers=merged_headers,
                    allow_redirects=allow_redirects
                )
                
                should_retry, reason = await self._handle_response(
                    response, url, retry
                )
                
                if not should_retry:
                    return response
                    
                if reason:
                    logger.warning(
                        "Retrying request to %s (%d/%d): %s",
                        url, retry + 1, self.max_retries, reason
                    )
                    
            except aiohttp.ClientError as e:
                if retry == self.max_retries:
                    raise DownloadError(
                        f"Failed to download {url}",
                        f"Error: {str(e)}"
                    )
                logger.warning(
                    "Request failed for %s (%d/%d): %s",
                    url, retry + 1, self.max_retries, str(e)
                )
                
        raise DownloadError(
            f"Failed to download {url}",
            "Max retries exceeded"
        )

def normalize_url(url: str) -> str:
    """Normalize URL by removing fragments and normalizing scheme."""
    try:
        parsed = urlparse(url)
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            fragment=''
        )
        return normalized.geturl()
    except Exception as e:
        logger.error("Failed to normalize URL %s: %s", url, str(e))
        return url

def join_urls(base: str, url: str) -> str:
    """Join URLs, handling edge cases."""
    try:
        # Handle edge cases with yarl
        base_url = URL(base)
        joined = urljoin(str(base_url), url)
        return normalize_url(joined)
    except Exception as e:
        logger.error("Failed to join URLs %s and %s: %s", base, url, str(e))
        return url 
