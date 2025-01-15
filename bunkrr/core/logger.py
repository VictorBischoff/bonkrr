"""Logging configuration for the bunkrr package."""
import logging
import sys
import traceback
from pathlib import Path
from typing import Optional, Union, Dict, Any

from .exceptions import BunkrrError

# Configure default logging format
DEFAULT_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

class BunkrrLogger:
    """Enhanced logger with error handling and formatting."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        """Initialize logger with name and level."""
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up console and file handlers."""
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)
        )
        self.logger.addHandler(console_handler)
        
        # File handler
        log_dir = Path.home() / '.bunkrr' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_dir / 'bunkrr.log',
            encoding='utf-8'
        )
        file_handler.setFormatter(
            logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)
        )
        self.logger.addHandler(file_handler)
    
    def debug(self, msg: str, *args, **kwargs):
        """Log debug message."""
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """Log info message."""
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning message."""
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, exc_info: bool = False, **kwargs):
        """Log error message with optional exception info."""
        self.logger.error(msg, *args, exc_info=exc_info, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log exception with traceback."""
        self.logger.exception(msg, *args, **kwargs)
    
    def log_error(self, error: Union[Exception, BunkrrError], context: str = '', **kwargs):
        """Log error with context and details."""
        if isinstance(error, BunkrrError):
            self.error(
                f"{context}: {error.message}",
                extra={'details': error.details} if error.details else None,
                **kwargs
            )
        else:
            self.exception(
                f"{context}: {str(error)}",
                extra={'traceback': traceback.format_exc()},
                **kwargs
            )

_loggers: Dict[str, BunkrrLogger] = {}

def setup_logger(name: str, level: int = logging.INFO) -> BunkrrLogger:
    """Get or create a logger instance."""
    if name not in _loggers:
        _loggers[name] = BunkrrLogger(name, level)
    return _loggers[name]

def log_exception(
    logger: BunkrrLogger,
    error: Exception,
    context: str,
    **kwargs: Any
) -> None:
    """Log an exception with context."""
    logger.log_error(error, context, **kwargs) 
