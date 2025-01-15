"""Custom Scrapy middlewares."""
from typing import Optional

from scrapy import signals
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from twisted.internet.defer import Deferred

from ..core.logger import setup_logger
from ..core.exceptions import ScrapyError
from ..downloader.rate_limiter import RateLimiter

logger = setup_logger('bunkrr.scrapy.middlewares')

class CustomRateLimiterMiddleware:
    """Middleware for rate limiting requests using a shared rate limiter."""
    
    def __init__(self):
        """Initialize the middleware."""
        self.rate_limiter: Optional[RateLimiter] = None
        logger.debug("Initialized CustomRateLimiterMiddleware")
        
    @classmethod
    def from_crawler(cls, crawler):
        """Create middleware instance from crawler."""
        middleware = cls()
        crawler.signals.connect(
            middleware.spider_opened,
            signal=signals.spider_opened
        )
        return middleware
        
    def spider_opened(self, spider: Spider):
        """Set up rate limiter when spider opens."""
        # Get rate limiter from spider
        self.rate_limiter = getattr(spider, 'rate_limiter', None)
        if not self.rate_limiter:
            logger.warning("No rate limiter found in spider %s", spider.name)
            
    async def process_request(self, request: Request, spider: Spider) -> Optional[Request]:
        """Process request through rate limiter."""
        if not self.rate_limiter:
            return None
            
        try:
            # Acquire token from rate limiter
            await self.rate_limiter.acquire()
            logger.debug("Acquired rate limit token for request: %s", request.url)
            return None
            
        except Exception as e:
            logger.error(
                "Error acquiring rate limit token: %s - %s",
                request.url,
                str(e),
                exc_info=True
            )
            raise ScrapyError(f"Rate limit error: {request.url}", str(e))
            
    def process_response(
        self,
        request: Request,
        response: Response,
        spider: Spider
    ) -> Response:
        """Process response to handle rate limit headers."""
        # Check for rate limit response
        if response.status == 429:  # Too Many Requests
            logger.warning(
                "Rate limit exceeded for request: %s (retry-after: %s)",
                request.url,
                response.headers.get('retry-after', 'unknown')
            )
            
        return response
