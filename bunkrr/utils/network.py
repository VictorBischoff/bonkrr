"""Network utilities for the bunkrr package."""
import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Set, Any, Union, Pattern
from urllib.parse import urljoin, urlparse, unquote
from pathlib import Path

import aiohttp
import aiodns
from aiohttp import (
    ClientResponse, ClientSession, ClientTimeout,
    TCPConnector, ClientError, ClientResponseError
)
from yarl import URL

from ..core.exceptions import (
    DownloadError, HTTPError, RateLimitError,
    ValidationError
)
from ..core.logger import setup_logger
from ..core.error_handler import ErrorHandler
from .storage import get_file_size, safe_remove
from .core import validate_path

logger = setup_logger('bunkrr.network')

@dataclass
class URLValidator:
    """URL validation with configurable patterns."""
    
    # Default patterns for Bunkr URLs
    domain_pattern: str = r'(?:(?:www|cdn|i-burger|media-files)\.)?bunkr\.(?:site|ru|ph|is|to|fi)'
    path_pattern: str = r'/(?:a|album|f|v)/[a-zA-Z0-9-_]{3,30}(?:/[^/]*)?$'
    protocol_pattern: str = r'^(?:https?://)?'
    
    # Compiled patterns
    url_pattern: Pattern = field(init=False)
    
    def __post_init__(self):
        """Compile regex pattern."""
        pattern = (
            self.protocol_pattern +
            self.domain_pattern +
            self.path_pattern
        )
        self.url_pattern = re.compile(pattern)
    
    def is_valid(self, url: str) -> bool:
        """Check if URL matches pattern."""
        return bool(self.url_pattern.match(url))
    
    def validate(self, url: str) -> None:
        """Validate URL and raise error if invalid."""
        if not url:
            raise ValidationError(
                message="URL cannot be empty",
                field="url",
                value=url
            )
        
        if not self.is_valid(url):
            raise ValidationError(
                message="Invalid URL format",
                field="url",
                value=url,
                details="URL must be a valid Bunkr album URL"
            )
    
    def validate_many(self, urls: List[str]) -> None:
        """Validate multiple URLs."""
        if not urls:
            raise ValidationError(
                message="No URLs provided",
                field="urls",
                value=urls
            )
        
        for url in urls:
            self.validate(url)

async def normalize_url(url: str) -> str:
    """Normalize URL by removing fragments and normalizing path.
    
    Args:
        url: URL to normalize
        
    Returns:
        Normalized URL string
    """
    parsed = URL(url)
    # Remove fragments and normalize path
    normalized = parsed.with_fragment(None).normalize()
    # Ensure scheme is https
    if not normalized.scheme:
        normalized = normalized.with_scheme('https')
    return str(normalized)

@dataclass
class HTTPConfig:
    """HTTP client configuration."""
    
    timeout: ClientTimeout = field(default_factory=lambda: ClientTimeout(total=30, connect=10))
    headers: Dict[str, str] = field(default_factory=lambda: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate'
    })
    pool_size: int = 100
    max_requests_per_host: int = 10
    retry_attempts: int = 3
    retry_delay: float = 1.0
    retry_codes: Set[int] = field(default_factory=lambda: {408, 429, 500, 502, 503, 504})

@dataclass
class DownloadConfig:
    """Download configuration."""
    
    chunk_size: int = 8192
    progress_callback: Optional[Any] = None
    skip_existing: bool = False
    overwrite: bool = False
    verify_hash: bool = True
    hash_algorithm: str = 'sha256'

class HTTPClient:
    """HTTP client with connection pooling and download capabilities."""
    
    def __init__(
        self,
        config: Optional[HTTPConfig] = None,
        download_config: Optional[DownloadConfig] = None
    ):
        """Initialize HTTP client with configuration."""
        self.config = config or HTTPConfig()
        self.download_config = download_config or DownloadConfig()
        
        self.connector = TCPConnector(
            limit=self.config.pool_size,
            limit_per_host=self.config.max_requests_per_host,
            enable_cleanup_closed=True
        )
        
        self.session = ClientSession(
            connector=self.connector,
            timeout=self.config.timeout,
            headers=self.config.headers,
            raise_for_status=True
        )
        
        self.resolver = aiodns.DNSResolver()
        self.active_requests: Set[str] = set()
    
    @ErrorHandler.wrap_async
    async def close(self) -> None:
        """Close client and cleanup resources."""
        try:
            if not self.session.closed:
                await self.session.close()
            await self.connector.close()
        except Exception as e:
            logger.error("Error closing HTTP client: %s", str(e))
            raise
    
    @ErrorHandler.wrap_async
    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[ClientTimeout] = None,
        retry: bool = True
    ) -> ClientResponse:
        """Send GET request with error handling and retries."""
        normalized_url = await self.normalize_url(url)
        self.active_requests.add(normalized_url)
        
        try:
            attempts = self.config.retry_attempts if retry else 1
            last_error = None
            
            for attempt in range(attempts):
                try:
                    response = await self.session.get(
                        normalized_url,
                        headers={**self.config.headers, **(headers or {})},
                        timeout=timeout or self.config.timeout
                    )
                    
                    # Check rate limit headers
                    if response.status == 429:
                        retry_after = float(response.headers.get('Retry-After', self.config.retry_delay))
                        raise RateLimitError(
                            message="Rate limit exceeded",
                            url=normalized_url,
                            retry_after=retry_after
                        )
                    
                    return response
                    
                except (ClientError, asyncio.TimeoutError) as e:
                    last_error = e
                    if isinstance(e, ClientResponseError):
                        if e.status not in self.config.retry_codes or attempt == attempts - 1:
                            raise HTTPError(
                                message=str(e),
                                url=normalized_url,
                                status_code=e.status,
                                details=str(e)
                            )
                    
                    if attempt < attempts - 1:
                        delay = self.config.retry_delay * (attempt + 1)
                        logger.warning(
                            "Request failed (attempt %d/%d), retrying in %.1f seconds: %s",
                            attempt + 1,
                            attempts,
                            delay,
                            str(e)
                        )
                        await asyncio.sleep(delay)
            
            raise HTTPError(
                message="Request failed after retries",
                url=normalized_url,
                details=str(last_error)
            )
            
        finally:
            self.active_requests.discard(normalized_url)
    
    @ErrorHandler.wrap_async
    async def download_file(
        self,
        url: str,
        destination: Union[str, Path],
        headers: Optional[Dict[str, str]] = None,
        config: Optional[DownloadConfig] = None
    ) -> Path:
        """Download file with progress tracking and validation."""
        cfg = config or self.download_config
        dest_path = validate_path(destination, create=True)
        
        if dest_path.exists():
            if cfg.skip_existing:
                logger.info("File exists, skipping: %s", dest_path)
                return dest_path
            if not cfg.overwrite:
                raise DownloadError(
                    message="File already exists",
                    url=url,
                    path=str(dest_path)
                )
        
        try:
            async with await self.get(url, headers=headers) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                hash_obj = hashlib.new(cfg.hash_algorithm) if cfg.verify_hash else None
                
                with dest_path.open('wb') as f:
                    async for chunk in response.content.iter_chunked(cfg.chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if hash_obj:
                            hash_obj.update(chunk)
                            
                        if cfg.progress_callback:
                            cfg.progress_callback(downloaded, total_size)
                
                # Verify hash if provided in headers
                if (
                    hash_obj and
                    (expected_hash := response.headers.get(f'X-{cfg.hash_algorithm}'))
                ):
                    actual_hash = hash_obj.hexdigest()
                    if actual_hash != expected_hash:
                        safe_remove(dest_path)
                        raise DownloadError(
                            message="Hash verification failed",
                            url=url,
                            path=str(dest_path),
                            details=f"Expected: {expected_hash}, Got: {actual_hash}"
                        )
                
                return dest_path
                
        except Exception as e:
            safe_remove(dest_path)
            if isinstance(e, (DownloadError, HTTPError)):
                raise
            raise DownloadError(
                message="Download failed",
                url=url,
                path=str(dest_path),
                details=str(e)
            )
    
    @staticmethod
    @ErrorHandler.wrap_async
    async def normalize_url(url: str) -> str:
        """Normalize URL by removing fragments and normalizing scheme."""
        parsed = urlparse(url)
        return parsed._replace(
            scheme=parsed.scheme.lower() or 'http',
            fragment='',
            path=parsed.path or '/'
        ).geturl()
    
    @staticmethod
    @ErrorHandler.wrap_async
    async def join_urls(base: str, url: str) -> str:
        """Join URLs, handling edge cases."""
        return await HTTPClient.normalize_url(urljoin(str(URL(base)), url))
    
    async def __aenter__(self):
        """Enter async context."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context and ensure cleanup."""
        try:
            await self.close()
        except Exception as e:
            logger.error("Error in HTTP client cleanup: %s", str(e))
            # Don't suppress the original exception if there was one
            if exc_type is None:
                raise

# Create global URL validator instance
url_validator = URLValidator()

# Convenience functions
def is_valid_url(url: str) -> bool:
    """Validate URL format."""
    return url_validator.is_valid(url)

def validate_url(url: str) -> None:
    """Validate URL and raise error if invalid."""
    url_validator.validate(url)

def validate_urls(urls: List[str]) -> None:
    """Validate multiple URLs."""
    url_validator.validate_many(urls) 
