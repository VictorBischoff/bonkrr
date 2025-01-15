"""Logging configuration for the application."""
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .exceptions import ConfigError

# Constants
DEFAULT_LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
DEFAULT_LOG_LEVEL = logging.INFO
MAX_BYTES = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5

def setup_logger(name: str, log_level: Optional[int] = None) -> logging.Logger:
    """Set up a logger with the given name and optional level."""
    logger = logging.getLogger(name)
    
    # Only configure handlers if they haven't been configured yet
    if not logger.handlers:
        logger.setLevel(log_level or DEFAULT_LOG_LEVEL)
        
        # Create formatters
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)
        detailed_formatter = logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s [%(filename)s:%(lineno)d]: %(message)s',
            DEFAULT_DATE_FORMAT
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        try:
            # Create logs directory if it doesn't exist
            logs_dir = Path('logs')
            logs_dir.mkdir(exist_ok=True)
            
            # Main log file with rotation
            main_log = logs_dir / 'bunkrr.log'
            file_handler = logging.handlers.RotatingFileHandler(
                main_log,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT
            )
            file_handler.setFormatter(detailed_formatter)
            logger.addHandler(file_handler)
            
            # Debug log file with rotation
            debug_log = logs_dir / 'debug.log'
            debug_handler = logging.handlers.RotatingFileHandler(
                debug_log,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT
            )
            debug_handler.setFormatter(detailed_formatter)
            debug_handler.setLevel(logging.DEBUG)
            logger.addHandler(debug_handler)
            
            # Error log file with rotation
            error_log = logs_dir / 'error.log'
            error_handler = logging.handlers.RotatingFileHandler(
                error_log,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT
            )
            error_handler.setFormatter(detailed_formatter)
            error_handler.setLevel(logging.ERROR)
            logger.addHandler(error_handler)
            
            # Scrapy specific log file
            if 'scrapy' in name:
                scrapy_log = logs_dir / 'scrapy.log'
                scrapy_handler = logging.handlers.RotatingFileHandler(
                    scrapy_log,
                    maxBytes=MAX_BYTES,
                    backupCount=BACKUP_COUNT
                )
                scrapy_handler.setFormatter(detailed_formatter)
                logger.addHandler(scrapy_handler)
                
        except Exception as e:
            raise ConfigError(f"Failed to set up log files: {e}")
        
    return logger

def log_exception(logger: logging.Logger, exc: Exception, context: str) -> None:
    """Log an exception with full traceback and context."""
    logger.error(
        "Exception in %s: %s",
        context,
        str(exc),
        exc_info=True,
        stack_info=True
    ) 
