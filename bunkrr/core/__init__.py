"""Core functionality for the bunkrr package."""
from .config import DownloadConfig
from .error_handler import ErrorHandler
from .decorators import handle_errors, handle_async_errors
from .exceptions import (
    BunkrrError,
    ConfigError,
    ValidationError,
    DownloadError,
    RateLimitError,
    FileSystemError,
    ScrapyError,
    HTTPError,
    ERROR_CODES
)
from .logger import setup_logger, log_exception

__all__ = [
    # Configuration
    'DownloadConfig',
    
    # Error handling
    'ErrorHandler',
    'handle_errors',
    'handle_async_errors',
    
    # Exceptions
    'BunkrrError',
    'ConfigError',
    'ValidationError',
    'DownloadError',
    'RateLimitError',
    'FileSystemError',
    'ScrapyError',
    'HTTPError',
    'ERROR_CODES',
    
    # Logging
    'setup_logger',
    'log_exception'
]
