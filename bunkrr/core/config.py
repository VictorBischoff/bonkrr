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
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, Optional, ClassVar, List
from enum import Enum
import json
import time

from .exceptions import ConfigError, ConfigVersionError
from .logger import setup_logger

logger = setup_logger('bunkrr.config')

class ConfigJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for configuration objects."""
    
    def default(self, obj: Any) -> Any:
        """Handle special types during JSON encoding.
        
        Args:
            obj: Object to encode
            
        Returns:
            JSON serializable representation
        """
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)

class ConfigValidationTracker:
    """Track configuration validation and changes."""
    
    def __init__(self):
        self.validation_count = 0
        self.validation_errors: List[Dict[str, Any]] = []
        self.last_validation = None
        self.changes: List[Dict[str, Any]] = []
    
    def add_validation(self, success: bool, config_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Record validation attempt."""
        self.validation_count += 1
        timestamp = time.time()
        
        if not success:
            self.validation_errors.append({
                'timestamp': timestamp,
                'config_type': config_type,
                'details': details or {}
            })
        
        self.last_validation = {
            'timestamp': timestamp,
            'success': success,
            'config_type': config_type,
            'details': details or {}
        }
        
        logger.debug(
            "Configuration validation - Type: %s, Success: %s, Details: %s",
            config_type,
            success,
            json.dumps(details or {}, cls=ConfigJSONEncoder)
        )
    
    def add_change(self, config_type: str, field: str, old_value: Any, new_value: Any) -> None:
        """Record configuration change."""
        change = {
            'timestamp': time.time(),
            'config_type': config_type,
            'field': field,
            'old_value': old_value,
            'new_value': new_value
        }
        self.changes.append(change)
        
        logger.info(
            "Configuration changed - Type: %s, Field: %s, Old: %s, New: %s",
            config_type,
            field,
            json.dumps(old_value, cls=ConfigJSONEncoder),
            json.dumps(new_value, cls=ConfigJSONEncoder)
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        stats = {
            'validation_count': self.validation_count,
            'error_count': len(self.validation_errors),
            'change_count': len(self.changes),
            'last_validation': self.last_validation,
            'recent_changes': self.changes[-5:] if self.changes else [],
            'recent_errors': self.validation_errors[-5:] if self.validation_errors else []
        }
        
        logger.debug(
            "Configuration stats - %s",
            json.dumps(stats, cls=ConfigJSONEncoder, indent=2)
        )
        return stats

# Global validation tracker
config_tracker = ConfigValidationTracker()

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
        latest = cls.V1_1
        logger.debug("Latest config version: %s", latest.value)
        return latest

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
    
    def __post_init__(self):
        """Validate settings after initialization."""
        logger.info(
            "Initializing ScrapyConfig - Version: %s",
            self.VERSION.value
        )
        self.validate()
    
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
        settings = {
            key: getattr(self, key)
            for key in self.__dataclass_fields__
            if not key.startswith('_') and key != 'VERSION'  # Exclude VERSION field
        }
        settings['version'] = str(self.VERSION.value)  # Add version as string
        
        logger.debug(
            "Converted ScrapyConfig to dict - Settings: %s",
            json.dumps(settings, cls=ConfigJSONEncoder)
        )
        return settings
    
    def validate(self) -> None:
        """Validate configuration settings.
        
        Raises:
            ConfigError: If any settings are invalid
        """
        try:
            # Validate concurrency settings
            if self.CONCURRENT_REQUESTS < 1:
                raise ConfigError("CONCURRENT_REQUESTS must be at least 1")
            if self.CONCURRENT_REQUESTS_PER_DOMAIN < 1:
                raise ConfigError("CONCURRENT_REQUESTS_PER_DOMAIN must be at least 1")
            if self.CONCURRENT_ITEMS < 1:
                raise ConfigError("CONCURRENT_ITEMS must be at least 1")
            
            # Validate timeout settings
            if self.DOWNLOAD_TIMEOUT < 1:
                raise ConfigError("DOWNLOAD_TIMEOUT must be at least 1")
            if self.RETRY_TIMES < 0:
                raise ConfigError("RETRY_TIMES must be non-negative")
            
            # Validate cache settings
            if self.DNSCACHE_SIZE < 100:
                raise ConfigError("DNSCACHE_SIZE must be at least 100")
            if self.HTTPCACHE_EXPIRATION_SECS < 0:
                raise ConfigError("HTTPCACHE_EXPIRATION_SECS must be non-negative")
            
            config_tracker.add_validation(True, 'ScrapyConfig', asdict(self))
            logger.info("ScrapyConfig validation successful")
            
        except ConfigError as e:
            details = {
                'error': str(e),
                'config': asdict(self)
            }
            config_tracker.add_validation(False, 'ScrapyConfig', details)
            logger.error(
                "ScrapyConfig validation failed - Error: %s, Config: %s",
                str(e),
                json.dumps(asdict(self))
            )
            raise

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
            logger.info(
                "Migrating ScrapyConfig - From version: %s, To version: %s",
                old_version,
                cls.VERSION.value
            )
            
            if old_ver == cls.VERSION:
                return cls(**old_config)
            
            # Add migration logic here as new versions are introduced
            raise ConfigVersionError(f"Migration from version {old_version} is not supported")
            
        except ValueError:
            error = f"Unknown configuration version: {old_version}"
            logger.error(
                "ScrapyConfig migration failed - Error: %s, Old config: %s",
                error,
                json.dumps(old_config)
            )
            raise ConfigVersionError(error)

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
    
    # Path settings
    downloads_path: Path = field(default_factory=lambda: Path.home() / 'Downloads' / 'bunkrr')
    
    # Rate limiting
    requests_per_window: int = 5
    window_size: int = 60  # seconds
    
    # Cache settings
    dns_cache_ttl: int = 300  # 5 minutes
    url_cache_size: int = 1024
    
    # Scrapy integration
    scrapy: ScrapyConfig = field(default_factory=ScrapyConfig)
    
    def __post_init__(self):
        """Validate settings after initialization."""
        logger.info(
            "Initializing DownloadConfig - Version: %s",
            self.VERSION.value
        )
        self.validate()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of the configuration
        """
        config_dict = {
            'version': str(self.VERSION.value),  # Convert enum to string
            'max_concurrent_downloads': self.max_concurrent_downloads,
            'chunk_size': self.chunk_size,
            'buffer_size': self.buffer_size,
            'connect_timeout': self.connect_timeout,
            'read_timeout': self.read_timeout,
            'total_timeout': self.total_timeout,
            'keep_alive_timeout': self.keep_alive_timeout,
            'downloads_path': str(self.downloads_path),
            'requests_per_window': self.requests_per_window,
            'window_size': self.window_size,
            'dns_cache_ttl': self.dns_cache_ttl,
            'url_cache_size': self.url_cache_size,
            'scrapy': self.scrapy.to_dict()
        }
        return config_dict
    
    def validate(self) -> None:
        """Validate configuration settings.
        
        Raises:
            ConfigError: If any settings are invalid
        """
        try:
            # Core settings validation
            if self.max_concurrent_downloads < 1:
                raise ConfigError("max_concurrent_downloads must be at least 1")
            if self.chunk_size < 1024:  # 1KB minimum
                raise ConfigError("chunk_size must be at least 1KB")
            if self.buffer_size < self.chunk_size:
                raise ConfigError("buffer_size must be at least as large as chunk_size")
            
            # Timeout validation
            if self.connect_timeout < 1:
                raise ConfigError("connect_timeout must be at least 1 second")
            if self.read_timeout < 1:
                raise ConfigError("read_timeout must be at least 1 second")
            if self.total_timeout < max(self.connect_timeout, self.read_timeout):
                raise ConfigError("total_timeout must be at least as large as the largest timeout")
            
            # Rate limiting validation
            if self.window_size < 1:
                raise ConfigError("window_size must be at least 1 second")
            if self.requests_per_window < 1:
                raise ConfigError("requests_per_window must be at least 1")
            
            # Cache validation
            if self.dns_cache_ttl < 0:
                raise ConfigError("dns_cache_ttl must be non-negative")
            if self.url_cache_size < 1:
                raise ConfigError("url_cache_size must be at least 1")
            
            # Validate Scrapy config
            self.scrapy.validate()
            
            config_tracker.add_validation(True, 'DownloadConfig', asdict(self))
            logger.info("DownloadConfig validation successful")
            
        except ConfigError as e:
            details = {
                'error': str(e),
                'config': asdict(self)
            }
            config_tracker.add_validation(False, 'DownloadConfig', details)
            logger.error(
                "DownloadConfig validation failed - Error: %s, Config: %s",
                str(e),
                json.dumps(asdict(self))
            )
            raise
    
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
            logger.info(
                "Migrating DownloadConfig - From version: %s, To version: %s",
                old_version,
                cls.VERSION.value
            )
            
            if old_ver == cls.VERSION:
                return cls(**old_config)
            
            # Add migration logic here as new versions are introduced
            raise ConfigVersionError(f"Migration from version {old_version} is not supported")
            
        except ValueError:
            error = f"Unknown configuration version: {old_version}"
            logger.error(
                "DownloadConfig migration failed - Error: %s, Old config: %s",
                error,
                json.dumps(old_config)
            )
            raise ConfigVersionError(error) 
