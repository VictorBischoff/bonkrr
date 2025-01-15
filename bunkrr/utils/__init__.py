"""Utility modules for the bunkrr package."""

# Network utilities
from .network import (
    HTTPClient, HTTPConfig, DownloadConfig,
    URLValidator, validate_url, validate_urls, is_valid_url
)

# Storage utilities
from .storage import (
    Cache, CacheConfig, CacheEntry,
    MemoryCache, FileCache, SQLiteCache,
    ensure_directory, get_file_size, safe_remove,
    sanitize_filename, get_unique_path
)

# Data utilities
from .data import (
    format_size, format_time, format_rate,
    create_progress_bar, ProgressData,
    DownloadStats, RateTracker, ProgressTracker,
    get_media_type, is_media_file, MEDIA_EXTENSIONS
)

# Core utilities
from .core import (
    CancellationToken,
    PathValidator, ConfigValidator,
    validate_path, validate_config
)

# Input utilities
from .input import (
    InputConfig, ConfigSchema, ConfigLoader,
    prompt_input, prompt_yes_no, prompt_choice,
    prompt_path, prompt_filename
)

__all__ = [
    # Network
    'HTTPClient', 'HTTPConfig', 'DownloadConfig',
    'URLValidator', 'validate_url', 'validate_urls', 'is_valid_url',
    
    # Storage
    'Cache', 'CacheConfig', 'CacheEntry',
    'MemoryCache', 'FileCache', 'SQLiteCache',
    'ensure_directory', 'get_file_size', 'safe_remove',
    'sanitize_filename', 'get_unique_path',
    
    # Data
    'format_size', 'format_time', 'format_rate',
    'create_progress_bar', 'ProgressData',
    'DownloadStats', 'RateTracker', 'ProgressTracker',
    'get_media_type', 'is_media_file', 'MEDIA_EXTENSIONS',
    
    # Core
    'CancellationToken',
    'PathValidator', 'ConfigValidator',
    'validate_path', 'validate_config',
    
    # Input
    'InputConfig', 'ConfigSchema', 'ConfigLoader',
    'prompt_input', 'prompt_yes_no', 'prompt_choice',
    'prompt_path', 'prompt_filename'
]
