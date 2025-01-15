"""Exception handling for the bunkrr package."""
from typing import Optional, Dict, Any

class BunkrrError(Exception):
    """Base exception class for all bunkrr errors."""
    
    def __init__(self, message: str, details: Optional[str] = None):
        """Initialize the error with a message and optional details."""
        super().__init__(message)
        self.message = message
        self.details = details
        
    def __str__(self) -> str:
        """Return a string representation of the error."""
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format."""
        return {
            'type': self.__class__.__name__,
            'message': self.message,
            'details': self.details
        }

class ConfigError(BunkrrError):
    """Error raised for configuration issues."""
    pass

class ValidationError(BunkrrError):
    """Error raised for validation failures."""
    pass

class DownloadError(BunkrrError):
    """Error raised for download failures."""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[str] = None
    ):
        """Initialize with download-specific information."""
        super().__init__(message, details)
        self.url = url
        self.status_code = status_code
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format with download info."""
        error_dict = super().to_dict()
        error_dict.update({
            'url': self.url,
            'status_code': self.status_code
        })
        return error_dict

class RateLimitError(BunkrrError):
    """Error raised for rate limiting issues."""
    pass

class FileSystemError(BunkrrError):
    """Error raised for filesystem operations."""
    
    def __init__(
        self,
        message: str,
        path: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[str] = None
    ):
        """Initialize with filesystem-specific information."""
        super().__init__(message, details)
        self.path = path
        self.operation = operation
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format with filesystem info."""
        error_dict = super().to_dict()
        error_dict.update({
            'path': self.path,
            'operation': self.operation
        })
        return error_dict

class ScrapyError(BunkrrError):
    """Error raised for Scrapy-related issues."""
    
    def __init__(
        self,
        message: str,
        spider_name: Optional[str] = None,
        url: Optional[str] = None,
        details: Optional[str] = None
    ):
        """Initialize with Scrapy-specific information."""
        super().__init__(message, details)
        self.spider_name = spider_name
        self.url = url
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format with Scrapy info."""
        error_dict = super().to_dict()
        error_dict.update({
            'spider_name': self.spider_name,
            'url': self.url
        })
        return error_dict

class HTTPError(BunkrrError):
    """Error raised for HTTP-related issues."""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[str] = None
    ):
        """Initialize with HTTP-specific information."""
        super().__init__(message, details)
        self.url = url
        self.method = method
        self.status_code = status_code
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format with HTTP info."""
        error_dict = super().to_dict()
        error_dict.update({
            'url': self.url,
            'method': self.method,
            'status_code': self.status_code
        })
        return error_dict

class ConfigVersionError(ConfigError):
    """Raised when there is a configuration version mismatch or migration error."""
    pass

class ShutdownError(BunkrrError):
    """Raised when there is an error during application shutdown."""
    pass

# Error codes for specific error types
ERROR_CODES = {
    ConfigError: 'CONFIG_ERROR',
    ValidationError: 'VALIDATION_ERROR',
    DownloadError: 'DOWNLOAD_ERROR',
    RateLimitError: 'RATE_LIMIT_ERROR',
    FileSystemError: 'FILESYSTEM_ERROR',
    ScrapyError: 'SCRAPY_ERROR',
    HTTPError: 'HTTP_ERROR'
} 
