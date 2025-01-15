"""Logging configuration for the bunkrr package."""
import logging
import logging.handlers
import os
import sys
import json
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from scrapy.utils.log import configure_logging

# Default log format with timestamp, level, and message
DEFAULT_FORMAT = (
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

# Detailed format for debugging with file and line info
DEBUG_FORMAT = (
    '%(asctime)s [%(levelname)s] %(name)s '
    '(%(filename)s:%(lineno)d): '
    '%(funcName)s: %(message)s'
)

# JSON format for structured logging
JSON_FORMAT = {
    'timestamp': '%(asctime)s',
    'level': '%(levelname)s',
    'logger': '%(name)s',
    'file': '%(filename)s',
    'line': '%(lineno)d',
    'function': '%(funcName)s',
    'message': '%(message)s',
    'spider': '%(spider)s',
    'duration': '%(duration)s'
}

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def __init__(
        self,
        fmt: Optional[Dict[str, str]] = None,
        datefmt: Optional[str] = None,
        style: str = '%'
    ):
        """Initialize formatter with optional format dictionary."""
        super().__init__(datefmt=datefmt)
        self.fmt_dict = fmt or JSON_FORMAT
        self.style = style
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        # Create base log entry
        log_entry = {}
        for key, fmt in self.fmt_dict.items():
            try:
                log_entry[key] = fmt % record.__dict__
            except (KeyError, TypeError):
                log_entry[key] = fmt
        
        # Add exception info if present
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            frames = []
            for frame in traceback.extract_tb(exc_tb):
                frames.append({
                    'file': frame.filename,
                    'line': frame.lineno,
                    'function': frame.name,
                    'code': frame.line
                })
            log_entry['exception'] = {
                'type': exc_type.__name__,
                'message': str(exc_value),
                'traceback': frames
            }
        
        # Add extra fields
        extra = {}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__:
                try:
                    json.dumps(value)  # Test JSON serialization
                    extra[key] = value
                except (TypeError, ValueError):
                    extra[key] = str(value)
        if extra:
            log_entry['extra'] = extra
        
        return json.dumps(log_entry)

class ConsoleFormatter(logging.Formatter):
    """Enhanced console formatter with color support."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m'   # Magenta
    }
    RESET = '\033[0m'
    
    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        style: str = '%',
        use_color: bool = True
    ):
        """Initialize formatter with color support."""
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.use_color = use_color and sys.stderr.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with optional color."""
        # Save original values
        orig_msg = record.msg
        orig_levelname = record.levelname
        
        if self.use_color:
            color = self.COLORS.get(record.levelname, self.RESET)
            record.levelname = f"{color}{record.levelname}{self.RESET}"
            if isinstance(record.msg, str):
                record.msg = f"{color}{record.msg}{self.RESET}"
        
        # Format message
        result = super().format(record)
        
        # Restore original values
        record.msg = orig_msg
        record.levelname = orig_levelname
        
        return result

def setup_logger(
    name: str,
    level: str = 'INFO',
    log_dir: Optional[str] = 'logs',
    console: bool = True,
    file: bool = True,
    json: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    scrapy_integration: bool = True
) -> logging.Logger:
    """Set up logger with standardized configuration."""
    # Get the root logger name (e.g., 'bunkrr' from 'bunkrr.scrapy.spiders')
    root_name = name.split('.')[0]
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    handlers: List[logging.Handler] = []
    
    if console:
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        if json:
            formatter = StructuredFormatter()
        else:
            formatter = ConsoleFormatter(
                fmt=DEBUG_FORMAT if level == 'DEBUG' else DEFAULT_FORMAT
            )
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)
    
    if file and log_dir:
        # Create log directory
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Main log file (INFO and above)
        main_log = log_dir / f"{root_name}.log"
        main_handler = logging.handlers.RotatingFileHandler(
            main_log,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.INFO)
        main_handler.setFormatter(
            StructuredFormatter() if json else ConsoleFormatter(fmt=DEFAULT_FORMAT)
        )
        handlers.append(main_handler)
        
        # Debug log file (all levels)
        debug_log = log_dir / f"{root_name}_debug.log"
        debug_handler = logging.handlers.RotatingFileHandler(
            debug_log,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(
            StructuredFormatter() if json else ConsoleFormatter(fmt=DEBUG_FORMAT)
        )
        handlers.append(debug_handler)
        
        # Error log file (ERROR and above)
        error_log = log_dir / f"{root_name}_error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(
            StructuredFormatter() if json else ConsoleFormatter(fmt=DEBUG_FORMAT)
        )
        handlers.append(error_handler)
    
    # Configure Scrapy logging integration
    if scrapy_integration:
        configure_logging(install_root_handler=False)
        logging.root.setLevel(level)
    
    # Add handlers to logger
    for handler in handlers:
        logger.addHandler(handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get or create logger with standard configuration.
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Use environment variables for configuration
        level = os.environ.get('LOG_LEVEL', 'INFO')
        log_dir = os.environ.get('LOG_DIR', 'logs')
        use_json = os.environ.get('LOG_JSON', '').lower() == 'true'
        
        logger = setup_logger(
            name,
            level=level,
            log_dir=log_dir,
            json=use_json,
            scrapy_integration=True
        )
    
    return logger

def log_exception(
    logger: logging.Logger,
    exc: Exception,
    message: str,
    *args: Any,
    level: str = 'ERROR',
    include_traceback: bool = True,
    include_context: bool = True,
    spider: Any = None,
    **kwargs: Any
) -> None:
    """Log an exception with enhanced context and formatting.
    
    Args:
        logger: Logger instance to use
        exc: Exception to log
        message: Message format string
        *args: Format string arguments
        level: Log level (default: ERROR)
        include_traceback: Whether to include traceback
        include_context: Whether to include exception context
        spider: Optional Scrapy spider instance
        **kwargs: Additional fields to log
    """
    # Get numeric level
    numeric_level = getattr(logging, level.upper(), logging.ERROR)
    
    # Format the main message
    if args:
        message = message % args
    
    # Build exception info
    exc_info = {
        'type': type(exc).__name__,
        'message': str(exc),
        'module': getattr(exc, '__module__', 'unknown')
    }
    
    # Add traceback if requested
    if include_traceback:
        exc_info['traceback'] = traceback.format_exception(
            type(exc),
            exc,
            exc.__traceback__
        )
    
    # Add context if requested and available
    if include_context and hasattr(exc, 'to_dict'):
        exc_info['context'] = exc.to_dict()
    
    # Add spider info if available
    if spider:
        exc_info['spider'] = {
            'name': spider.name,
            'stats': getattr(spider, 'stats', {})
        }
    
    # Add any additional kwargs
    if kwargs:
        exc_info['extra'] = kwargs
    
    # Log with full context
    extra = {'spider': spider} if spider else {}
    logger.log(
        numeric_level,
        "%s - %s",
        message,
        json.dumps(exc_info, indent=2),
        exc_info=include_traceback,
        extra=extra
    ) 
