"""Configuration management for the bunkrr package."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Dict, Any

def get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable with fallback."""
    try:
        if value := os.getenv(key):
            return int(value)
    except ValueError:
        pass
    return default

def get_env_path(key: str, default: Path) -> Path:
    """Get path from environment variable with fallback."""
    if value := os.getenv(key):
        return Path(value)
    return default

@dataclass
class DownloadConfig:
    """Configuration settings for downloads with environment variable support."""
    # Rate limiting - Optimized defaults based on empirical data
    max_concurrent_downloads: int = get_env_int('BUNKRR_MAX_CONCURRENT', 6)  # Reduced from 12
    rate_limit: int = get_env_int('BUNKRR_RATE_LIMIT', 5)  # Reduced from 10
    rate_window: int = get_env_int('BUNKRR_RATE_WINDOW', 60)  # Increased from 30
    
    # Download path
    downloads_path: Path = get_env_path('BUNKRR_DOWNLOADS_PATH', Path('downloads'))
    
    # File handling - Optimized for modern network speeds
    chunk_size: int = get_env_int('BUNKRR_CHUNK_SIZE', 262144)  # 256KB chunks for better throughput
    min_file_size: int = get_env_int('BUNKRR_MIN_FILE_SIZE', 10 * 1024)  # 10KB minimum
    download_timeout: int = get_env_int('BUNKRR_TIMEOUT', 180)  # 3 minutes, balanced timeout
    
    # Retry settings - More aggressive retry strategy
    max_retries: int = get_env_int('BUNKRR_MAX_RETRIES', 5)  # Increased for better reliability
    retry_delay: int = get_env_int('BUNKRR_RETRY_DELAY', 10)  # Increased from 3
    
    # Valid file types
    valid_extensions: FrozenSet[str] = frozenset({
        # Images
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff',
        # Videos
        '.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv',
        # Audio
        '.mp3', '.m4a', '.wav', '.ogg', '.flac',
        # Archives
        '.zip', '.rar', '.7z', '.tar', '.gz'
    })
    
    # Valid domains
    valid_domains: FrozenSet[str] = frozenset({'.site', '.ru', '.ph', '.is', '.to', '.fi'})
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate_config()
        self._log_config()
    
    def _validate_config(self):
        """Validate configuration values."""
        if self.max_concurrent_downloads < 1:
            raise ValueError("max_concurrent_downloads must be at least 1")
        if self.rate_limit < 1:
            raise ValueError("rate_limit must be at least 1")
        if self.chunk_size < 1024:
            raise ValueError("chunk_size must be at least 1KB")
        if self.download_timeout < 30:
            raise ValueError("download_timeout must be at least 30 seconds")
            
    def _log_config(self):
        """Log current configuration for debugging."""
        from .logger import setup_logger
        logger = setup_logger('bunkrr.config')
        
        config_dict = {
            'max_concurrent_downloads': self.max_concurrent_downloads,
            'rate_limit': self.rate_limit,
            'rate_window': self.rate_window,
            'downloads_path': str(self.downloads_path),
            'chunk_size': self.chunk_size,
            'min_file_size': self.min_file_size,
            'download_timeout': self.download_timeout,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay
        }
        
        logger.info(
            "Configuration loaded",
            extra={'config': config_dict}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            'max_concurrent_downloads': self.max_concurrent_downloads,
            'rate_limit': self.rate_limit,
            'rate_window': self.rate_window,
            'downloads_path': str(self.downloads_path),
            'chunk_size': self.chunk_size,
            'min_file_size': self.min_file_size,
            'download_timeout': self.download_timeout,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay
        } 
