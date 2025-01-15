"""Logging configuration for the bunkrr package."""
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Default log format with timestamp, level, and message
DEFAULT_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

# Detailed format for debugging with file and line info
DEBUG_FORMAT = (
    '%(asctime)s [%(levelname)s] %(name)s '
    '(%(filename)s:%(lineno)d): %(message)s'
)

class ErrorLogFilter(logging.Filter):
    """Filter to enhance error log records with additional context."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add error context to log record if available."""
        if hasattr(record, 'extra'):
            for key, value in record.extra.items():
                setattr(record, key, value)
        return True

class BunkrrLogger:
    """Logger configuration for the bunkrr package."""
    
    def __init__(
        self,
        name: str,
        level: str = 'INFO',
        log_dir: Optional[Path] = None,
        max_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5
    ):
        """Initialize logger configuration."""
        self.name = name
        self.level = getattr(logging, level.upper())
        self.log_dir = log_dir or Path('logs')
        self.max_size = max_size
        self.backup_count = backup_count
        
        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.level)
        
        # Add error context filter
        self.logger.addFilter(ErrorLogFilter())
        
        # Setup handlers if not already configured
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """Setup console and file handlers."""
        # Create log directory if needed
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(self.level)
        console.setFormatter(logging.Formatter(
            DEFAULT_FORMAT if self.level > logging.DEBUG else DEBUG_FORMAT
        ))
        self.logger.addHandler(console)
        
        # File handlers
        handlers = {
            'error': (logging.ERROR, 'error.log'),
            'info': (logging.INFO, 'info.log'),
            'debug': (logging.DEBUG, 'debug.log')
        }
        
        for name, (level, filename) in handlers.items():
            if self.level <= level:
                handler = logging.handlers.RotatingFileHandler(
                    self.log_dir / filename,
                    maxBytes=self.max_size,
                    backupCount=self.backup_count
                )
                handler.setLevel(level)
                handler.setFormatter(logging.Formatter(
                    DEBUG_FORMAT if level <= logging.DEBUG else DEFAULT_FORMAT
                ))
                self.logger.addHandler(handler)
    
    def get_logger(self) -> logging.Logger:
        """Get configured logger instance."""
        return self.logger

def setup_logger(
    name: str,
    level: str = 'INFO',
    log_dir: Optional[Path] = None
) -> logging.Logger:
    """Setup and return a configured logger instance."""
    logger_config = BunkrrLogger(name, level, log_dir)
    return logger_config.get_logger()

def log_exception(logger: logging.Logger, exc: Exception, context: str) -> None:
    """Log an exception with full traceback and context."""
    logger.error(
        "Exception in %s: %s",
        context,
        str(exc),
        exc_info=True,
        stack_info=True
    ) 
