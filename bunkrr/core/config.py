"""Configuration management for the bunkrr package."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional

from .exceptions import ConfigError
from .logger import setup_logger

logger = setup_logger('bunkrr.config')

@dataclass
class ScrapyConfig:
    """Scrapy-specific configuration settings."""
    ROBOTSTXT_OBEY: bool = False
    COOKIES_ENABLED: bool = False
    CONCURRENT_REQUESTS: int = 16
    CONCURRENT_REQUESTS_PER_DOMAIN: int = 8
    DOWNLOAD_TIMEOUT: int = 30
    RETRY_ENABLED: bool = True
    RETRY_TIMES: int = 3
    RETRY_HTTP_CODES: list = field(default_factory=lambda: [500, 502, 503, 504, 522, 524, 408, 429])
    DOWNLOADER_MIDDLEWARES: Dict[str, int] = field(default_factory=lambda: {
        'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
        'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 110,
        'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
        'scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware': None,
    })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for Scrapy settings."""
        return {
            key: getattr(self, key)
            for key in self.__dataclass_fields__
            if not key.startswith('_')
        }

@dataclass
class DownloadConfig:
    """Download configuration settings."""
    downloads_path: Path = Path.home() / 'Downloads' / 'bunkrr'
    max_concurrent_downloads: int = 8
    rate_limit: int = 5
    rate_window: int = 60
    retry_delay: int = 10
    max_retries: int = 3
    min_file_size: int = 1024  # 1KB
    download_timeout: int = 300  # 5 minutes
    scrapy: ScrapyConfig = field(default_factory=ScrapyConfig)
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        try:
            self._validate_paths()
            self._validate_limits()
            self._validate_timeouts()
            logger.info("Configuration validated successfully")
        except Exception as e:
            raise ConfigError(f"Invalid configuration: {str(e)}")
    
    def _validate_paths(self):
        """Validate and create necessary paths."""
        if not isinstance(self.downloads_path, Path):
            self.downloads_path = Path(self.downloads_path)
        
        try:
            self.downloads_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ConfigError(
                f"Failed to create downloads directory: {self.downloads_path}",
                details=str(e)
            )
    
    def _validate_limits(self):
        """Validate rate limits and concurrent downloads."""
        if self.max_concurrent_downloads < 1:
            raise ConfigError("max_concurrent_downloads must be at least 1")
        if self.rate_limit < 1:
            raise ConfigError("rate_limit must be at least 1")
        if self.rate_window < 1:
            raise ConfigError("rate_window must be at least 1 second")
    
    def _validate_timeouts(self):
        """Validate timeout settings."""
        if self.download_timeout < 1:
            raise ConfigError("download_timeout must be at least 1 second")
        if self.retry_delay < 0:
            raise ConfigError("retry_delay cannot be negative")
        if self.max_retries < 0:
            raise ConfigError("max_retries cannot be negative") 
