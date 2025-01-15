"""Validation utilities for the bunkrr package."""
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urlparse

from ..core.exceptions import ValidationError
from ..core.logger import setup_logger
from .filesystem import is_valid_path

logger = setup_logger('bunkrr.validation')

# Compile regex patterns for better performance
URL_PATTERN = re.compile(
    r'^https?://(?:www\.)?'
    r'(?:bunkr\.(?:site|ru|ph|is|to|fi))'
    r'/[a-zA-Z0-9-_/]+$'
)

ALBUM_ID_PATTERN = re.compile(r'[a-zA-Z0-9-_]{3,30}')

class URLValidator:
    """URL validation with caching."""
    
    def __init__(self):
        """Initialize validator with allowed domains."""
        self.allowed_domains: Set[str] = {
            'bunkr.site',
            'bunkr.ru',
            'bunkr.ph',
            'bunkr.is',
            'bunkr.to',
            'bunkr.fi'
        }
    
    @lru_cache(maxsize=1024)
    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid with caching."""
        try:
            # Basic URL pattern check
            if not URL_PATTERN.match(url):
                return False
            
            # Parse URL
            parsed = urlparse(url)
            
            # Check domain
            if parsed.netloc not in self.allowed_domains:
                return False
            
            # Check path
            path = parsed.path.strip('/')
            if not path:
                return False
            
            # Check album ID format
            album_id = path.split('/')[-1]
            if not ALBUM_ID_PATTERN.match(album_id):
                return False
            
            return True
            
        except Exception as e:
            logger.error("URL validation error: %s - %s", url, str(e))
            return False
    
    def validate_url(self, url: str) -> None:
        """Validate URL and raise error if invalid."""
        if not url:
            raise ValidationError("URL cannot be empty")
            
        if not self.is_valid_url(url):
            raise ValidationError(
                f"Invalid URL: {url}",
                "URL must be a valid Bunkr album URL"
            )
    
    def validate_urls(self, urls: List[str]) -> None:
        """Validate multiple URLs."""
        if not urls:
            raise ValidationError("No URLs provided")
            
        for url in urls:
            self.validate_url(url)

def validate_download_path(path: Optional[Path]) -> None:
    """Validate download path."""
    if not path:
        raise ValidationError("Download path cannot be empty")
        
    try:
        # Convert string to Path if needed
        if isinstance(path, str):
            path = Path(path)
        
        # Check if path is valid
        if not is_valid_path(path):
            raise ValidationError(
                f"Invalid download path: {path}",
                "Path must be writable"
            )
            
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(f"Invalid download path: {path}", str(e))

def validate_config_value(name: str, value: Any, min_val: Optional[Any] = None, max_val: Optional[Any] = None) -> None:
    """Validate configuration value."""
    if value is None:
        raise ValidationError(f"{name} cannot be None")
        
    if min_val is not None and value < min_val:
        raise ValidationError(f"{name} must be at least {min_val}")
        
    if max_val is not None and value > max_val:
        raise ValidationError(f"{name} must be at most {max_val}")

# Create global URL validator instance
url_validator = URLValidator() 
