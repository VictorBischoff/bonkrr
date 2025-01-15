"""Custom Scrapy middlewares."""
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, List, Pattern
import asyncio
import time
import re
from datetime import datetime
from urllib.parse import urlparse

from scrapy import signals
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.exceptions import IgnoreRequest

from ..core.logger import setup_logger
from ..core.error_handler import ErrorHandler
from ..core.exceptions import ScrapyError, ValidationError
from ..downloader.rate_limiter import RateLimiter

logger = setup_logger('bunkrr.scrapy.middlewares')

@dataclass
class DomainState:
    """Domain-specific rate limiting state."""
    last_request: float = field(default_factory=time.monotonic)
    min_interval: float = 0.5
    active_requests: Set[str] = field(default_factory=set)
    
    def update_interval(self, retry_after: float) -> None:
        """Update minimum interval based on retry-after value."""
        self.min_interval = max(self.min_interval, retry_after / 2)
    
    async def wait_if_needed(self) -> None:
        """Wait if minimum interval hasn't elapsed."""
        now = time.monotonic()
        elapsed = now - self.last_request
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self.last_request = time.monotonic()

@dataclass
class RequestValidator:
    """Request validation configuration."""
    allowed_domains: Set[str] = field(default_factory=set)
    allowed_paths: List[Pattern] = field(default_factory=list)
    max_depth: int = 3
    
    @classmethod
    def from_spider(cls, spider: Spider) -> 'RequestValidator':
        """Create validator from spider attributes."""
        allowed_domains = set(getattr(spider, 'allowed_domains', []))
        allowed_paths = [
            re.compile(pattern)
            for pattern in getattr(spider, 'allowed_paths', [])
        ]
        max_depth = getattr(spider, 'max_depth', 3)
        return cls(allowed_domains, allowed_paths, max_depth)
    
    def validate_request(self, request: Request) -> None:
        """Validate request against rules."""
        url_parts = urlparse(request.url)
        domain = url_parts.netloc
        path = url_parts.path
        depth = request.meta.get('depth', 0)
        
        if domain not in self.allowed_domains:
            raise ValidationError(
                message="Domain not allowed",
                field="domain",
                value=domain
            )
        
        if self.allowed_paths and not any(p.match(path) for p in self.allowed_paths):
            raise ValidationError(
                message="Path not allowed",
                field="path",
                value=path
            )
        
        if depth > self.max_depth:
            raise ValidationError(
                message="Maximum depth exceeded",
                field="depth",
                value=depth
            )

class SpiderMiddleware:
    """Spider middleware for request validation and error handling."""
    
    def __init__(self):
        """Initialize middleware."""
        self.stats: Dict[str, int] = {
            'processed': 0,
            'filtered': 0,
            'errors': 0
        }
        self.validator: Optional[RequestValidator] = None
    
    @classmethod
    def from_crawler(cls, crawler):
        """Create middleware from crawler."""
        middleware = cls()
        crawler.signals.connect(
            middleware.spider_opened,
            signal=signals.spider_opened
        )
        return middleware
    
    def spider_opened(self, spider: Spider) -> None:
        """Configure validator when spider opens."""
        self.validator = RequestValidator.from_spider(spider)
        logger.debug(
            "Spider middleware initialized for %s with domains: %s",
            spider.name,
            self.validator.allowed_domains
        )
    
    @ErrorHandler.wrap
    def process_spider_input(self, response: Response, spider: Spider) -> None:
        """Process response before passing to spider."""
        self.stats['processed'] += 1
    
    @ErrorHandler.wrap
    def process_spider_output(
        self,
        response: Response,
        result: List[Request],
        spider: Spider
    ) -> List[Request]:
        """Filter and validate requests from spider."""
        filtered_requests = []
        
        for request in result:
            try:
                if isinstance(request, Request):
                    self.validator.validate_request(request)
                    filtered_requests.append(request)
                else:
                    filtered_requests.append(request)
            except ValidationError as e:
                self.stats['filtered'] += 1
                logger.debug(
                    "Filtered request to %s: %s",
                    request.url,
                    e.message
                )
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(
                    "Error processing request to %s: %s",
                    request.url,
                    str(e)
                )
        
        return filtered_requests
    
    @ErrorHandler.wrap
    def process_spider_exception(
        self,
        response: Response,
        exception: Exception,
        spider: Spider
    ) -> None:
        """Handle spider exceptions."""
        self.stats['errors'] += 1
        logger.error(
            "Spider error processing %s: %s",
            response.url,
            str(exception),
            exc_info=True
        )

class RateLimitMiddleware:
    """Middleware for rate limiting requests with domain-specific limits."""
    
    def __init__(self):
        """Initialize middleware."""
        self.rate_limiter: Optional[RateLimiter] = None
        self.domains: Dict[str, DomainState] = {}
        logger.debug("Initialized RateLimitMiddleware")
    
    @classmethod
    def from_crawler(cls, crawler):
        """Create middleware from crawler."""
        middleware = cls()
        crawler.signals.connect(
            middleware.spider_opened,
            signal=signals.spider_opened
        )
        return middleware
    
    def spider_opened(self, spider: Spider) -> None:
        """Configure rate limiter when spider opens."""
        self.rate_limiter = getattr(spider, 'rate_limiter', None)
        if not self.rate_limiter:
            logger.warning("No rate limiter found in spider %s", spider.name)
    
    def _get_domain_state(self, url: str) -> DomainState:
        """Get or create domain state."""
        domain = url.split('/')[2]
        if domain not in self.domains:
            self.domains[domain] = DomainState()
        return self.domains[domain]
    
    @ErrorHandler.wrap_async
    async def process_request(self, request: Request, spider: Spider) -> Optional[Request]:
        """Process request with domain-specific rate limiting."""
        if not self.rate_limiter:
            return None
        
        try:
            state = self._get_domain_state(request.url)
            state.active_requests.add(request.url)
            
            # Wait for domain cooldown and rate limiter
            await state.wait_if_needed()
            await self.rate_limiter.acquire()
            
            logger.debug("Rate limit token acquired for: %s", request.url)
            return None
            
        except Exception as e:
            logger.error(
                "Rate limit error for %s: %s",
                request.url,
                str(e)
            )
            raise ScrapyError(
                message="Rate limit error",
                url=request.url,
                details=str(e)
            )
        finally:
            state.active_requests.discard(request.url)
    
    @ErrorHandler.wrap
    def process_response(
        self,
        request: Request,
        response: Response,
        spider: Spider
    ) -> Response:
        """Handle rate limit responses and update domain limits."""
        if response.status == 429:
            retry_after = response.headers.get('retry-after')
            if retry_after:
                try:
                    wait_time = float(retry_after.decode())
                    state = self._get_domain_state(request.url)
                    state.update_interval(wait_time)
                    
                    logger.warning(
                        "Rate limit exceeded for %s (retry after: %s)",
                        request.url,
                        wait_time
                    )
                except (ValueError, AttributeError) as e:
                    logger.error(
                        "Invalid retry-after header for %s: %s",
                        request.url,
                        str(e)
                    )
        
        return response
