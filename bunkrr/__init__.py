"""Bunkrr - A media downloader for Bunkr.site."""

__version__ = '0.1.0'
__author__ = 'Victor'
__description__ = 'A fast and efficient downloader for Bunkr.site'

from .core.config import DownloadConfig
from .core.error_handler import (
    ErrorHandler,
    handle_errors,
    handle_async_errors
)
from .core.exceptions import (
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
from .core.logger import setup_logger
from .downloader.downloader import Downloader
from .scrapy import MediaProcessor
from .ui.console import ConsoleUI

__all__ = [
    # Core functionality
    'DownloadConfig',
    'setup_logger',
    
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
    
    # Main components
    'Downloader',
    'MediaProcessor',
    'ConsoleUI'
]
