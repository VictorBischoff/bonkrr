"""Storage utilities for the bunkrr package."""
import json
import os
import pickle
import sqlite3
import sys
import time
import weakref
import zlib
from collections import OrderedDict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Set, Tuple, Union, List, Protocol, runtime_checkable

from ..core.exceptions import BunkrrError, CacheError, FileSystemError
from ..core.logger import setup_logger
from ..core.error_handler import ErrorHandler

logger = setup_logger('bunkrr.storage')

@runtime_checkable
class Cache(Protocol):
    """Base cache protocol defining the interface for all cache implementations."""
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        ...
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        ...
    
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        ...
    
    def clear(self) -> None:
        """Clear all values from cache."""
        ...
    
    def has(self, key: str) -> bool:
        """Check if key exists in cache."""
        ...
    
    def get_size(self) -> int:
        """Get current cache size."""
        ...

@dataclass
class CacheConfig:
    """Cache configuration."""
    
    name: str
    ttl: Optional[int] = None
    max_size: Optional[int] = None
    compress: bool = True
    compression_level: int = 6
    batch_size: int = 100  # Number of items to evict in batch
    
    # File cache specific
    cache_dir: Optional[Union[str, Path]] = None
    
    # SQLite specific
    db_path: Optional[Union[str, Path]] = None
    pool_size: int = 5

class CacheEntry:
    """Cache entry with metadata and lazy size calculation."""
    
    __slots__ = ('value', 'timestamp', '_size', '__weakref__')
    
    def __init__(self, value: Any, timestamp: float = None):
        """Initialize cache entry."""
        self.value = value
        self.timestamp = timestamp or time.time()
        self._size: Optional[int] = None
    
    @property
    def size(self) -> int:
        """Get size of cached value in bytes (calculated lazily)."""
        if self._size is None:
            try:
                self._size = len(pickle.dumps(self.value))
            except Exception:
                self._size = 1
        return self._size
    
    def is_expired(self, ttl: Optional[int]) -> bool:
        """Check if entry is expired."""
        if ttl is None:
            return False
        return time.time() - self.timestamp > ttl
    
    def to_bytes(self, compress: bool = True, level: int = 6) -> bytes:
        """Convert entry to bytes."""
        try:
            data = pickle.dumps((self.value, self.timestamp))
            if compress:
                return zlib.compress(data, level)
            return data
        except Exception as e:
            raise CacheError(f"Failed to serialize cache entry: {e}")
    
    @classmethod
    def from_bytes(cls, data: bytes, compress: bool = True) -> 'CacheEntry':
        """Create entry from bytes."""
        try:
            if compress:
                data = zlib.decompress(data)
            value, timestamp = pickle.loads(data)
            return cls(value, timestamp)
        except Exception as e:
            raise CacheError(f"Failed to deserialize cache entry: {e}")

class MemoryCache:
    """In-memory cache implementation with optimized LRU eviction."""
    
    def __init__(self, config: CacheConfig):
        """Initialize memory cache."""
        self.config = config
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._size = 0
        self._pending_eviction: deque[str] = deque()
        self._string_pool: Dict[str, str] = {}  # String interning pool
    
    def _intern_key(self, key: str) -> str:
        """Intern string key to reduce memory usage."""
        if key in self._string_pool:
            return self._string_pool[key]
        self._string_pool[key] = key
        return key
    
    def _evict_batch(self) -> None:
        """Evict a batch of items if cache exceeds max size."""
        if not self.config.max_size or not self._pending_eviction:
            return
            
        # Process pending evictions in batches
        batch_size = min(len(self._pending_eviction), self.config.batch_size)
        for _ in range(batch_size):
            try:
                key = self._pending_eviction.popleft()
                if key in self._cache:
                    entry = self._cache.pop(key)
                    self._size -= entry.size
                    logger.debug("Evicted item %s from cache %s", key, self.config.name)
            except IndexError:
                break
    
    def _check_eviction(self, new_size: int) -> None:
        """Check if eviction is needed and queue items."""
        if not self.config.max_size:
            return
            
        while self._size + new_size > self.config.max_size and self._cache:
            # Queue oldest items for eviction
            key, _ = next(iter(self._cache.items()))
            self._pending_eviction.append(key)
            
        # Perform batch eviction
        if len(self._pending_eviction) >= self.config.batch_size:
            self._evict_batch()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        key = self._intern_key(key)
        if key not in self._cache:
            return None
            
        entry = self._cache[key]
        if entry.is_expired(self.config.ttl):
            self.delete(key)
            return None
            
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return entry.value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        key = self._intern_key(key)
        entry = CacheEntry(value)
        
        # Remove old entry if exists
        if key in self._cache:
            old_entry = self._cache[key]
            self._size -= old_entry.size
        
        # Check eviction before adding
        self._check_eviction(entry.size)
        
        # Add new entry
        self._cache[key] = entry
        self._size += entry.size
        
        # Move to end (most recently used)
        self._cache.move_to_end(key)
    
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        key = self._intern_key(key)
        if key in self._cache:
            entry = self._cache.pop(key)
            self._size -= entry.size
    
    def clear(self) -> None:
        """Clear all values from cache."""
        self._cache.clear()
        self._size = 0
        self._pending_eviction.clear()
        self._string_pool.clear()
    
    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        key = self._intern_key(key)
        if key not in self._cache:
            return False
            
        entry = self._cache[key]
        if entry.is_expired(self.config.ttl):
            self.delete(key)
            return False
            
        return True
    
    def get_size(self) -> int:
        """Get current cache size."""
        return self._size

class FileCache(Cache):
    """File-based cache implementation."""
    
    def __init__(self, config: CacheConfig):
        """Initialize file cache."""
        super().__init__(config)
        if not config.cache_dir:
            raise CacheError("cache_dir is required for FileCache")
            
        self.cache_dir = Path(config.cache_dir) / config.name
        ensure_directory(self.cache_dir)
        self._size = self._calculate_total_size()
    
    def _get_path(self, key: str) -> Path:
        """Get cache file path for key."""
        return self.cache_dir / f"{key}.cache"
    
    def _calculate_total_size(self) -> int:
        """Calculate total size of cache directory."""
        total = 0
        for path in self.cache_dir.glob("*.cache"):
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total
    
    def _evict_if_needed(self, new_size: int) -> None:
        """Evict files if cache would exceed max size."""
        if self.config.max_size is None:
            return
            
        while self._size + new_size > self.config.max_size:
            # Get oldest file
            try:
                files = sorted(
                    self.cache_dir.glob("*.cache"),
                    key=lambda p: p.stat().st_mtime
                )
                if not files:
                    break
                    
                oldest = files[0]
                size = oldest.stat().st_size
                oldest.unlink()
                self._size -= size
                logger.debug(
                    "Evicted file %s from cache %s",
                    oldest.name,
                    self.config.name
                )
            except OSError:
                break
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache file."""
        path = self._get_path(key)
        if not path.exists():
            return None
            
        try:
            entry = CacheEntry.from_bytes(
                path.read_bytes(),
                compress=self.config.compress
            )
            
            if entry.is_expired(self.config.ttl):
                self.delete(key)
                return None
                
            return entry.value
            
        except Exception as e:
            logger.error("Failed to read cache file: %s", e)
            self.delete(key)
            return None
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache file."""
        path = self._get_path(key)
        entry = CacheEntry(value)
        
        try:
            # Get size of new data
            data = entry.to_bytes(
                compress=self.config.compress,
                level=self.config.compression_level
            )
            new_size = len(data)
            
            # Remove old file if exists
            if path.exists():
                old_size = path.stat().st_size
                self._size -= old_size
            
            # Evict if needed
            self._evict_if_needed(new_size)
            
            # Write new file
            path.write_bytes(data)
            self._size += new_size
            
        except Exception as e:
            logger.error("Failed to write cache file: %s", e)
            self.delete(key)
    
    def delete(self, key: str) -> None:
        """Delete cache file."""
        path = self._get_path(key)
        try:
            if path.exists():
                size = path.stat().st_size
                path.unlink()
                self._size -= size
        except OSError as e:
            logger.error("Failed to delete cache file: %s", e)
    
    def clear(self) -> None:
        """Clear all cache files."""
        try:
            for path in self.cache_dir.glob("*.cache"):
                try:
                    path.unlink()
                except OSError:
                    continue
            self._size = 0
        except OSError as e:
            logger.error("Failed to clear cache directory: %s", e)
    
    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None
    
    def get_size(self) -> int:
        """Get current cache size."""
        return self._size

class SQLiteCache:
    """SQLite-based cache implementation."""
    
    def __init__(self, config: CacheConfig):
        """Initialize SQLite cache."""
        super().__init__()
        if not config.db_path:
            raise CacheError("db_path is required for SQLiteCache")
            
        self.config = config
        self.db_path = Path(config.db_path)
        self._connections: List[sqlite3.Connection] = []
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        value BLOB NOT NULL,
                        timestamp REAL NOT NULL,
                        size INTEGER NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp 
                    ON cache(timestamp)
                """)
                conn.commit()
        except sqlite3.Error as e:
            raise CacheError(f"Failed to initialize SQLite cache: {e}")
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection from the pool."""
        conn = None
        try:
            # Try to reuse an existing connection
            for existing_conn in self._connections:
                try:
                    existing_conn.execute("SELECT 1")
                    conn = existing_conn
                    break
                except sqlite3.Error:
                    continue
            
            # Create new connection if needed
            if conn is None and len(self._connections) < self.config.pool_size:
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=30.0,
                    isolation_level=None
                )
                conn.execute("PRAGMA journal_mode=WAL")
                self._connections.append(conn)
            
            if conn is None:
                raise CacheError("No available database connections")
                
            yield conn
            
        except sqlite3.Error as e:
            raise CacheError(f"Database error: {e}")
            
        except Exception as e:
            raise CacheError(f"Unexpected error: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value, timestamp FROM cache WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return None
                    
                value_bytes, timestamp = row
                entry = CacheEntry.from_bytes(
                    value_bytes,
                    compress=self.config.compress
                )
                
                if entry.is_expired(self.config.ttl):
                    self.delete(key)
                    return None
                    
                return entry.value
                
        except CacheError:
            raise
        except Exception as e:
            raise CacheError(f"Failed to get value: {e}")
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        try:
            entry = CacheEntry(value)
            value_bytes = entry.to_bytes(
                compress=self.config.compress,
                level=self.config.compression_level
            )
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if we need to evict
                if self.config.max_size is not None:
                    current_size = self.get_size()
                    if current_size + len(value_bytes) > self.config.max_size:
                        # Remove oldest entries until we have space
                        cursor.execute("""
                            DELETE FROM cache 
                            WHERE key IN (
                                SELECT key FROM cache 
                                ORDER BY timestamp ASC 
                                LIMIT -1 OFFSET ?
                            )
                        """, (self.config.batch_size,))
                
                # Insert or replace value
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO cache (key, value, timestamp, size)
                    VALUES (?, ?, ?, ?)
                    """,
                    (key, value_bytes, entry.timestamp, len(value_bytes))
                )
                conn.commit()
                
        except CacheError:
            raise
        except Exception as e:
            raise CacheError(f"Failed to set value: {e}")
    
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
        except Exception as e:
            raise CacheError(f"Failed to delete value: {e}")
    
    def clear(self) -> None:
        """Clear all values from cache."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM cache")
                conn.commit()
        except Exception as e:
            raise CacheError(f"Failed to clear cache: {e}")
    
    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None
    
    def get_size(self) -> int:
        """Get current cache size in bytes."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COALESCE(SUM(size), 0) FROM cache")
                return cursor.fetchone()[0]
        except Exception as e:
            raise CacheError(f"Failed to get cache size: {e}")
    
    def __del__(self) -> None:
        """Close all database connections."""
        for conn in self._connections:
            try:
                conn.close()
            except Exception:
                pass
        self._connections.clear()

# Filesystem utilities
def ensure_directory(path: Path) -> None:
    """Ensure directory exists and is writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        if not os.access(path, os.W_OK):
            raise FileSystemError(
                message="Directory not writable",
                path=str(path),
                operation="create"
            )
    except Exception as e:
        if isinstance(e, FileSystemError):
            raise
        raise FileSystemError(
            message="Failed to create directory",
            path=str(path),
            operation="create",
            details=str(e)
        )

def get_file_size(path: Path) -> int:
    """Get file size in bytes."""
    try:
        return path.stat().st_size
    except Exception as e:
        raise FileSystemError(
            message="Failed to get file size",
            path=str(path),
            operation="stat",
            details=str(e)
        )

def safe_remove(path: Path) -> None:
    """Safely remove file if it exists."""
    try:
        if path.exists():
            path.unlink()
    except Exception as e:
        logger.error("Failed to remove file %s: %s", path, e)

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for filesystem."""
    # Remove invalid characters
    safe_name = "".join(c for c in filename if c.isalnum() or c in "- _.")
    # Remove leading/trailing spaces and dots
    safe_name = safe_name.strip(". ")
    # Ensure filename is not empty
    if not safe_name:
        safe_name = "unnamed"
    return safe_name[:255]  # Limit length

def get_unique_path(path: Path) -> Path:
    """Get unique path by appending number if needed."""
    if not path.exists():
        return path
        
    counter = 1
    while True:
        stem = path.stem
        suffix = path.suffix
        new_path = path.with_name(f"{stem}_{counter}{suffix}")
        if not new_path.exists():
            return new_path
        counter += 1

def is_valid_path(path: Path) -> bool:
    """Check if path is valid and writable."""
    try:
        if path.exists():
            return os.access(path, os.W_OK)
        return os.access(path.parent, os.W_OK)
    except Exception:
        return False 
