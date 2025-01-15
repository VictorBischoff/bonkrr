"""Exception classes for the bunkrr package."""
from typing import Optional, Dict, Any

class BunkrrError(Exception):
    """Base exception class for bunkrr package."""
    
    def __init__(
        self,
        message: str,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize base error."""
        super().__init__(message)
        self.message = message
        self.details = details
        self.extra = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary."""
        return {
            'type': self.__class__.__name__,
            'message': self.message,
            'details': self.details,
            **self.extra
        }

class HTTPError(BunkrrError):
    """HTTP request error."""
    
    def __init__(
        self,
        message: str,
        method: str,
        url: str,
        status_code: Optional[int] = None,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize HTTP error."""
        super().__init__(
            message,
            details=details,
            method=method,
            url=url,
            status_code=status_code,
            **kwargs
        )
        self.method = method
        self.url = url
        self.status_code = status_code

class DownloadError(BunkrrError):
    """Media download error."""
    
    def __init__(
        self,
        message: str,
        url: str,
        status_code: Optional[int] = None,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize download error."""
        super().__init__(
            message,
            details=details,
            url=url,
            status_code=status_code,
            **kwargs
        )
        self.url = url
        self.status_code = status_code

class ValidationError(BunkrrError):
    """Data validation error."""
    
    def __init__(
        self,
        message: str,
        field: str,
        value: Any,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize validation error."""
        super().__init__(
            message,
            details=details,
            field=field,
            value=value,
            **kwargs
        )
        self.field = field
        self.value = value

class ConfigError(BunkrrError):
    """Configuration error."""
    
    def __init__(
        self,
        message: str,
        key: str,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize config error."""
        super().__init__(
            message,
            details=details,
            key=key,
            **kwargs
        )
        self.key = key

class ConfigVersionError(ConfigError):
    """Configuration version error."""
    
    def __init__(
        self,
        message: str,
        version: Optional[str] = None,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize version error.
        
        Args:
            message: Error message
            version: Version string that caused the error
            details: Optional error details
            **kwargs: Additional error context
        """
        super().__init__(
            message,
            key='version',
            details=details,
            version=version,
            **kwargs
        )
        self.version = version

class ScrapyError(BunkrrError):
    """Scrapy spider error."""
    
    def __init__(
        self,
        message: str,
        spider: str,
        url: str,
        status_code: Optional[int] = None,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize scrapy error."""
        super().__init__(
            message,
            details=details,
            spider=spider,
            url=url,
            status_code=status_code,
            **kwargs
        )
        self.spider = spider
        self.url = url
        self.status_code = status_code

class SpiderError(ScrapyError):
    """Spider-specific error with enhanced context."""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        spider_name: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize spider error.
        
        Args:
            message: Error message
            url: Optional URL that caused the error
            spider_name: Optional name of the spider
            status_code: Optional HTTP status code
            details: Optional error details
            **kwargs: Additional error context
        """
        super().__init__(
            message=message,
            spider=spider_name or 'unknown',
            url=url or 'unknown',
            status_code=status_code,
            details=details,
            **kwargs
        )
        self.spider_name = spider_name

class ShutdownError(BunkrrError):
    """Error raised when application shutdown is requested."""
    
    def __init__(
        self,
        message: str = "Application shutdown requested",
        reason: Optional[str] = None,
        clean: bool = True,
        **kwargs: Any
    ):
        """Initialize shutdown error.
        
        Args:
            message: Error message
            reason: Optional reason for shutdown
            clean: Whether this is a clean shutdown
            **kwargs: Additional error context
        """
        super().__init__(
            message,
            details=reason,
            clean_shutdown=clean,
            **kwargs
        )
        self.reason = reason
        self.clean = clean

class ParsingError(BunkrrError):
    """Data parsing error."""
    
    def __init__(
        self,
        message: str,
        data_type: str,
        source: str,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize parsing error."""
        super().__init__(
            message,
            details=details,
            data_type=data_type,
            source=source,
            **kwargs
        )
        self.data_type = data_type
        self.source = source

class RateLimitError(BunkrrError):
    """Rate limit exceeded error."""
    
    def __init__(
        self,
        message: str,
        url: str,
        retry_after: Optional[float] = None,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize rate limit error."""
        super().__init__(
            message,
            details=details,
            url=url,
            retry_after=retry_after,
            **kwargs
        )
        self.url = url
        self.retry_after = retry_after

class FileSystemError(BunkrrError):
    """File system operation error."""
    
    def __init__(
        self,
        message: str,
        path: str,
        operation: str,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize filesystem error."""
        super().__init__(
            message,
            details=details,
            path=path,
            operation=operation,
            **kwargs
        )
        self.path = path
        self.operation = operation

class CacheError(BunkrrError):
    """Cache operation error."""
    
    def __init__(
        self,
        message: str,
        key: str,
        operation: str,
        details: Optional[str] = None,
        **kwargs: Any
    ):
        """Initialize cache error.
        
        Args:
            message: Error message
            key: Cache key that caused the error
            operation: Cache operation that failed (get/set/delete)
            details: Optional error details
            **kwargs: Additional error context
        """
        super().__init__(
            message,
            details=details,
            key=key,
            operation=operation,
            **kwargs
        )
        self.key = key
        self.operation = operation

# Error codes mapping
ERROR_CODES = {
    ConfigError: 'CONFIG_ERROR',
    ValidationError: 'VALIDATION_ERROR',
    DownloadError: 'DOWNLOAD_ERROR',
    RateLimitError: 'RATE_LIMIT_ERROR',
    FileSystemError: 'FILESYSTEM_ERROR',
    ScrapyError: 'SCRAPY_ERROR',
    HTTPError: 'HTTP_ERROR',
    ParsingError: 'PARSING_ERROR',
    CacheError: 'CACHE_ERROR'
} 
