"""Configuration management for the bunkrr package.

This module provides configuration management for the Bunkrr application, including
version tracking, validation, and migration utilities. It uses dataclasses for
type-safe configuration with proper validation.

Key Components:
    - ConfigVersion: Version enumeration for configuration
    - ScrapyConfig: Scrapy-specific settings configuration
    - DownloadConfig: Main download settings configuration

Example Usage:
    >>> from bunkrr.core.config import DownloadConfig
    >>> config = DownloadConfig()
    >>> config.max_concurrent_downloads = 4
    >>> config.validate()  # Validates all settings
    >>>
    >>> # Migrate from old config
    >>> old_config = {'max_concurrent_downloads': 8}
    >>> new_config = DownloadConfig.migrate_from(old_config, "1.0")

Version Migration:
    When upgrading between versions, use the migrate_from classmethod:
    >>> old_config = load_old_config()  # Your loading logic
    >>> new_config = DownloadConfig.migrate_from(old_config, "1.0")
    
    The migration system will handle any necessary conversions and validations.

See Also:
    - bunkrr.core.exceptions: Configuration-related exceptions
    - bunkrr.core.logger: Logging utilities
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, ClassVar
from enum import Enum

from .exceptions import ConfigError, ConfigVersionError
from .logger import setup_logger

logger = setup_logger('bunkrr.config')

class ConfigVersion(Enum):
    """Configuration version enumeration.
    
    This enum tracks configuration versions and provides utilities for version
    comparison and migration. Each version represents a specific configuration
    schema.
    
    Attributes:
        V1_0: Initial configuration version
        V1_1: Current version with enhanced settings
        
    Example:
        >>> version = ConfigVersion.latest()
        >>> print(version.value)
        '1.1'
    """
    V1_0 = "1.0"
    V1_1 = "1.1"  # Current version
    
    @classmethod
    def latest(cls) -> 'ConfigVersion':
        """Get the latest configuration version.
        
        Returns:
            The most recent ConfigVersion enum value.
            
        Example:
            >>> latest = ConfigVersion.latest()
            >>> assert latest == ConfigVersion.V1_1
        """
        return cls.V1_1

@dataclass
class ScrapyConfig:
    """Scrapy-specific configuration settings.
    
    This class manages Scrapy-specific settings with proper validation and
    version tracking. It includes settings for concurrency, timeouts,
    caching, and middleware configuration.
    
    Attributes:
        VERSION: Current configuration version
        ROBOTSTXT_OBEY: Whether to respect robots.txt
        COOKIES_ENABLED: Whether to enable cookie handling
        LOG_ENABLED: Whether to enable Scrapy logging
        COMPRESSION_ENABLED: Whether to enable response compression
        
    Example:
        >>> config = ScrapyConfig()
        >>> config.CONCURRENT_REQUESTS = 16
        >>> settings = config.to_dict()
        >>> print(settings['CONCURRENT_REQUESTS'])
        16
    """
    VERSION: ClassVar[ConfigVersion] = ConfigVersion.V1_1
    
    # Core Settings
    ROBOTSTXT_OBEY: bool = False
    COOKIES_ENABLED: bool = False
    LOG_ENABLED: bool = True
    COMPRESSION_ENABLED: bool = True
    
    # Concurrency Settings
    CONCURRENT_REQUESTS: int = 32  # Increased from 16
    CONCURRENT_REQUESTS_PER_DOMAIN: int = 16  # Increased from 8
    CONCURRENT_ITEMS: int = 200
    REACTOR_THREADPOOL_MAXSIZE: int = 20
    
    # Timeout and Retry Settings
    DOWNLOAD_TIMEOUT: int = 30
    RETRY_ENABLED: bool = True
    RETRY_TIMES: int = 3
    RETRY_HTTP_CODES: list = field(default_factory=lambda: [500, 502, 503, 504, 522, 524, 408, 429])
    RETRY_PRIORITY_ADJUST: int = -1
    
    # Memory and Cache Settings
    DNSCACHE_ENABLED: bool = True
    DNSCACHE_SIZE: int = 10000
    HTTPCACHE_ENABLED: bool = True
    HTTPCACHE_EXPIRATION_SECS: int = 3600
    HTTPCACHE_GZIP: bool = True
    
    # Download Settings
    DOWNLOAD_MAXSIZE: int = 1073741824  # 1GB
    DOWNLOAD_WARNSIZE: int = 33554432   # 32MB
    DOWNLOAD_FAIL_ON_DATALOSS: bool = False
    
    # Middleware Settings
    DOWNLOADER_MIDDLEWARES: Dict[str, int] = field(default_factory=lambda: {
        'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
        'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 110,
        'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
        'scrapy.downloadermiddlewares.defaultheaders.DefaultHeadersMiddleware': None,
        'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 590,
        'scrapy.downloadermiddlewares.stats.DownloaderStats': 850,
        'bunkrr.scrapy.middlewares.CustomRateLimiterMiddleware': 450,
    })
    
    # Performance Settings
    REACTOR_THREADPOOL_MAXSIZE: int = 20
    TWISTED_REACTOR: str = 'twisted.internet.asyncio.AsyncioSelectorReactor'
    ASYNCIO_EVENT_LOOP: str = 'uvloop.EventLoop'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for Scrapy settings.
        
        Returns:
            Dictionary of Scrapy settings ready for use.
            
        Example:
            >>> config = ScrapyConfig()
            >>> settings = config.to_dict()
            >>> print(settings['COMPRESSION_ENABLED'])
            True
        """
        return {
            key: getattr(self, key)
            for key in self.__dataclass_fields__
            if not key.startswith('_')
        }

    @classmethod
    def migrate_from(cls, old_config: Dict[str, Any], old_version: str) -> 'ScrapyConfig':
        """Migrate configuration from an older version.
        
        This method handles the migration of configuration settings between
        different versions, ensuring compatibility and proper validation.
        
        Args:
            old_config: The old configuration dictionary
            old_version: The version string of the old configuration
            
        Returns:
            A new ScrapyConfig instance with migrated settings
            
        Raises:
            ConfigVersionError: If migration from the specified version is not supported
            
        Example:
            >>> old_config = {'CONCURRENT_REQUESTS': 8}
            >>> config = ScrapyConfig.migrate_from(old_config, "1.0")
            >>> print(config.CONCURRENT_REQUESTS)
            8
        """
        try:
            old_ver = ConfigVersion(old_version)
        except ValueError:
            raise ConfigVersionError(f"Unknown configuration version: {old_version}")
            
        if old_ver == cls.VERSION:
            return cls(**old_config)
            
        # Add migration logic here as new versions are introduced
        raise ConfigVersionError(f"Migration from version {old_version} is not supported")

@dataclass
class DownloadConfig:
    """Main download configuration settings."""
    VERSION: ClassVar[ConfigVersion] = ConfigVersion.V1_1
    
    # Core settings
    max_concurrent_downloads: int = 6
    chunk_size: int = 65536  # 64KB
    buffer_size: int = 1048576  # 1MB
    connect_timeout: int = 30
    read_timeout: int = 300
    total_timeout: int = 600
    keep_alive_timeout: int = 60
    
    # Rate limiting
    requests_per_window: int = 5
    window_size: int = 60  # seconds
    
    # Cache settings
    dns_cache_ttl: int = 300  # 5 minutes
    url_cache_size: int = 1024
    
    # Scrapy integration
    scrapy: ScrapyConfig = field(default_factory=ScrapyConfig)
    
    @classmethod
    def migrate_from(cls, old_config: Dict[str, Any], old_version: str) -> 'DownloadConfig':
        """Migrate configuration from an older version.
        
        Args:
            old_config: The old configuration dictionary
            old_version: The version string of the old configuration
            
        Returns:
            A new DownloadConfig instance with migrated settings
            
        Raises:
            ConfigVersionError: If migration from the specified version is not supported
        """
        try:
            old_ver = ConfigVersion(old_version)
        except ValueError:
            raise ConfigVersionError(f"Unknown configuration version: {old_version}")
            
        if old_ver == cls.VERSION:
            return cls(**old_config)
            
        # Add migration logic here as new versions are introduced
        raise ConfigVersionError(f"Migration from version {old_version} is not supported")
        
    def validate(self) -> None:
        """Validate configuration settings.
        
        Raises:
            ConfigError: If any settings are invalid
        """
        if self.max_concurrent_downloads < 1:
            raise ConfigError("max_concurrent_downloads must be at least 1")
        if self.chunk_size < 1024:  # 1KB minimum
            raise ConfigError("chunk_size must be at least 1KB")
        if self.buffer_size < self.chunk_size:
            raise ConfigError("buffer_size must be at least as large as chunk_size")
        if self.window_size < 1:
            raise ConfigError("window_size must be at least 1 second")
        if self.requests_per_window < 1:
            raise ConfigError("requests_per_window must be at least 1") 
