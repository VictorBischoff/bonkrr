"""Custom Scrapy middlewares."""
from typing import Optional, Dict, List
import asyncio
import time

from scrapy import signals
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from twisted.internet.defer import Deferred

from ..core.logger import setup_logger
from ..core.exceptions import ScrapyError
from ..downloader.rate_limiter import RateLimiter

logger = setup_logger('bunkrr.scrapy.middlewares')

class CustomRateLimiterMiddleware:
    """Middleware for rate limiting requests using a shared rate limiter with request batching."""
    
    def __init__(self):
        """Initialize the middleware."""
        self.rate_limiter: Optional[RateLimiter] = None
        self._batch_size = 5  # Process requests in batches
        self._batch_timeout = 0.1  # Maximum wait time for batch
        self._request_queue: List[Request] = []
        self._batch_lock = asyncio.Lock()
        self._processing = False
        self._domain_timestamps: Dict[str, float] = {}
        self._min_domain_interval = 0.5  # Minimum time between requests to same domain
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
            
    async def _process_batch(self) -> None:
        """Process a batch of requests."""
        if not self._request_queue:
            return
            
        async with self._batch_lock:
            # Take up to batch_size requests
            batch = self._request_queue[:self._batch_size]
            self._request_queue = self._request_queue[self._batch_size:]
            
            # Process batch concurrently
            tasks = []
            for request in batch:
                domain = request.url.split('/')[2]
                last_time = self._domain_timestamps.get(domain, 0)
                now = time.monotonic()
                
                # Ensure minimum interval between requests to same domain
                if now - last_time < self._min_domain_interval:
                    wait_time = self._min_domain_interval - (now - last_time)
                    await asyncio.sleep(wait_time)
                
                self._domain_timestamps[domain] = time.monotonic()
                tasks.append(self.rate_limiter.acquire())
            
            # Wait for all rate limit tokens
            await asyncio.gather(*tasks)
            
    async def process_request(self, request: Request, spider: Spider) -> Optional[Request]:
        """Process request through rate limiter with batching."""
        if not self.rate_limiter:
            return None
            
        try:
            # Add request to queue
            self._request_queue.append(request)
            
            # Start batch processing if not already running
            if not self._processing:
                self._processing = True
                try:
                    while self._request_queue:
                        await self._process_batch()
                        # Small delay between batches
                        await asyncio.sleep(0.01)
                finally:
                    self._processing = False
            
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
        """Process response to handle rate limit headers with adaptive rate limiting."""
        # Check for rate limit response
        if response.status == 429:  # Too Many Requests
            retry_after = response.headers.get('retry-after')
            if retry_after:
                try:
                    wait_time = float(retry_after.decode())
                    logger.warning(
                        "Rate limit exceeded for request: %s (retry-after: %s)",
                        request.url,
                        wait_time
                    )
                    # Adjust domain interval if needed
                    domain = request.url.split('/')[2]
                    self._min_domain_interval = max(
                        self._min_domain_interval,
                        wait_time / 2
                    )
                except (ValueError, AttributeError):
                    pass
            
        return response
