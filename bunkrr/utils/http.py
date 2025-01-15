"""HTTP utilities for the bunkrr package."""
import asyncio
import socket
from typing import Dict, Optional, Tuple, Union, List, Set
from urllib.parse import urljoin, urlparse
from collections import defaultdict

import aiohttp
import aiodns
from aiohttp import (
    ClientResponse, ClientSession, ClientTimeout,
    TCPConnector, ClientError
)
from yarl import URL

from ..core.exceptions import DownloadError, HTTPError
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.http')

# Default timeout settings
DEFAULT_TIMEOUT = ClientTimeout(total=30, connect=10)

# Default connection limits
DEFAULT_POOL_SIZE = 100
DEFAULT_MAX_REQUESTS_PER_HOST = 10
DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 30
DEFAULT_KEEPALIVE_TIMEOUT = 30

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

class DNSCache:
    """DNS cache with TTL support."""
    
    def __init__(self, ttl: int = 300):
        """Initialize DNS cache."""
        self.ttl = ttl
        self._cache: Dict[str, Tuple[List[str], float]] = {}
        self._resolver = aiodns.DNSResolver()
        
    async def resolve(self, hostname: str) -> List[str]:
        """Resolve hostname with caching."""
        now = asyncio.get_event_loop().time()
        
        # Check cache
        if hostname in self._cache:
            addresses, timestamp = self._cache[hostname]
            if now - timestamp < self.ttl:
                return addresses
                
        # Resolve
        try:
            result = await self._resolver.query(hostname, 'A')
            addresses = [r.host for r in result]
            self._cache[hostname] = (addresses, now)
            return addresses
        except Exception as e:
            logger.error("DNS resolution failed for %s: %s", hostname, e)
            raise HTTPError(f"DNS resolution failed: {e}")

class RequestQueue:
    """Request queue with per-host rate limiting."""
    
    def __init__(self, max_requests_per_host: int = DEFAULT_MAX_REQUESTS_PER_HOST):
        """Initialize request queue."""
        self.max_requests_per_host = max_requests_per_host
        self._active_requests: Dict[str, int] = defaultdict(int)
        self._queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        
    async def acquire(self, hostname: str) -> None:
        """Acquire slot for request to hostname."""
        if self._active_requests[hostname] >= self.max_requests_per_host:
            # Wait for slot
            queue = self._queues[hostname]
            await queue.put(None)
            await queue.get()
            
        self._active_requests[hostname] += 1
        
    def release(self, hostname: str) -> None:
        """Release slot for hostname."""
        self._active_requests[hostname] = max(0, self._active_requests[hostname] - 1)
        
        # Notify waiting requests
        queue = self._queues[hostname]
        if not queue.empty():
            queue.get_nowait()
            queue.put_nowait(None)

class HTTPClient:
    """HTTP client with connection pooling and request queuing."""
    
    def __init__(
        self,
        timeout: Optional[Union[float, ClientTimeout]] = None,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        retry_codes: Optional[Set[int]] = None,
        pool_size: int = DEFAULT_POOL_SIZE,
        max_requests_per_host: int = DEFAULT_MAX_REQUESTS_PER_HOST,
        keepalive_timeout: int = DEFAULT_KEEPALIVE_TIMEOUT,
        max_keepalive_connections: int = DEFAULT_MAX_KEEPALIVE_CONNECTIONS,
        dns_cache_ttl: int = 300
    ):
        """Initialize HTTP client."""
        self.timeout = timeout or DEFAULT_TIMEOUT
        if isinstance(self.timeout, (int, float)):
            self.timeout = ClientTimeout(total=float(self.timeout))
            
        self.headers = {**DEFAULT_HEADERS, **(headers or {})}
        self.max_retries = max_retries
        self.retry_codes = retry_codes or {408, 429, 500, 502, 503, 504}
        
        # Connection management
        self._connector = TCPConnector(
            limit=pool_size,
            limit_per_host=max_requests_per_host,
            keepalive_timeout=keepalive_timeout,
            force_close=False,
            enable_cleanup_closed=True
        )
        
        self._session: Optional[ClientSession] = None
        self._dns_cache = DNSCache(ttl=dns_cache_ttl)
        self._request_queue = RequestQueue(max_requests_per_host)
        
    async def __aenter__(self) -> 'HTTPClient':
        """Create session on enter."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                connector=self._connector,
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
    
    async def _resolve_url(self, url: Union[str, URL]) -> Tuple[str, str]:
        """Resolve URL to hostname and address."""
        if isinstance(url, str):
            url = URL(url)
            
        hostname = url.host
        try:
            addresses = await self._dns_cache.resolve(hostname)
            return hostname, addresses[0]
        except Exception as e:
            logger.error("Failed to resolve %s: %s", hostname, e)
            raise HTTPError(f"Failed to resolve {hostname}: {e}")
    
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
            error_msg = f"{error_msg}: {await response.text()}"
        except Exception:
            pass
            
        raise HTTPError(error_msg)
    
    async def request(
        self,
        method: str,
        url: Union[str, URL],
        **kwargs
    ) -> ClientResponse:
        """Make HTTP request with retries and queuing."""
        hostname, address = await self._resolve_url(url)
        
        for retry in range(self.max_retries + 1):
            try:
                # Wait for available slot
                await self._request_queue.acquire(hostname)
                
                try:
                    response = await self.session.request(
                        method,
                        url,
                        **kwargs
                    )
                    
                    should_retry, reason = await self._handle_response(
                        response,
                        str(url),
                        retry
                    )
                    
                    if not should_retry:
                        return response
                        
                    logger.warning(
                        "Retrying request to %s (%s)",
                        url,
                        reason
                    )
                    
                finally:
                    self._request_queue.release(hostname)
                    
            except (ClientError, asyncio.TimeoutError) as e:
                if retry == self.max_retries:
                    raise HTTPError(f"Request failed after {retry + 1} attempts: {e}")
                    
                logger.warning(
                    "Request to %s failed (attempt %d/%d): %s",
                    url,
                    retry + 1,
                    self.max_retries + 1,
                    str(e)
                )
                
        raise HTTPError(f"Request failed after {self.max_retries + 1} attempts")
    
    async def get(self, url: Union[str, URL], **kwargs) -> ClientResponse:
        """Make GET request."""
        return await self.request('GET', url, **kwargs)
    
    async def post(self, url: Union[str, URL], **kwargs) -> ClientResponse:
        """Make POST request."""
        return await self.request('POST', url, **kwargs)
    
    async def head(self, url: Union[str, URL], **kwargs) -> ClientResponse:
        """Make HEAD request."""
        return await self.request('HEAD', url, **kwargs)

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
