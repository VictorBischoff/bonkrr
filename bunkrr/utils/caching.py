"""Caching utilities for the bunkrr package."""
import json
import os
import pickle
import sqlite3
import time
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Set, Tuple, Union, List

from ..core.exceptions import BunkrrError, CacheError
from ..core.logger import setup_logger
from .filesystem import ensure_directory

logger = setup_logger('bunkrr.caching')

class Cache:
    """Base class for caching implementations."""
    
    def __init__(self, name: str, ttl: Optional[int] = None, max_size: Optional[int] = None):
        """Initialize cache with name, TTL in seconds, and optional size limit."""
        self.name = name
        self.ttl = ttl
        self.max_size = max_size
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        raise NotImplementedError
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        raise NotImplementedError
    
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        raise NotImplementedError
    
    def clear(self) -> None:
        """Clear all values from cache."""
        raise NotImplementedError
    
    def has(self, key: str) -> bool:
        """Check if key exists in cache."""
        raise NotImplementedError

    def get_size(self) -> int:
        """Get current cache size."""
        raise NotImplementedError

class MemoryCache(Cache):
    """In-memory cache implementation with LRU eviction."""
    
    def __init__(self, name: str, ttl: Optional[int] = None, max_size: Optional[int] = None):
        """Initialize memory cache with LRU eviction."""
        super().__init__(name, ttl, max_size)
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._size = 0
    
    def _is_expired(self, timestamp: float) -> bool:
        """Check if cache entry is expired."""
        if self.ttl is None:
            return False
        return time.time() - timestamp > self.ttl
    
    def _get_item_size(self, value: Any) -> int:
        """Estimate size of cached item in bytes."""
        try:
            return len(pickle.dumps(value))
        except Exception:
            return 1
    
    def _evict_if_needed(self, new_item_size: int) -> None:
        """Evict items if cache would exceed max size."""
        if self.max_size is None:
            return
            
        while self._size + new_item_size > self.max_size and self._cache:
            # Remove oldest item (LRU)
            key, (value, _) = self._cache.popitem(last=False)
            self._size -= self._get_item_size(value)
            logger.debug("Evicted item %s from cache %s", key, self.name)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with LRU update."""
        if key not in self._cache:
            return None
            
        value, timestamp = self._cache[key]
        if self._is_expired(timestamp):
            self.delete(key)
            return None
            
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache with size management."""
        item_size = self._get_item_size(value)
        
        if self.max_size and item_size > self.max_size:
            raise CacheError(
                f"Item size ({item_size} bytes) exceeds cache max size "
                f"({self.max_size} bytes)"
            )
            
        # Remove old entry size if exists
        if key in self._cache:
            old_value, _ = self._cache[key]
            self._size -= self._get_item_size(old_value)
            
        self._evict_if_needed(item_size)
        self._cache[key] = (value, time.time())
        self._size += item_size
    
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        if key in self._cache:
            value, _ = self._cache[key]
            self._size -= self._get_item_size(value)
            del self._cache[key]
    
    def clear(self) -> None:
        """Clear all values from cache."""
        self._cache.clear()
        self._size = 0
    
    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        if key not in self._cache:
            return False
            
        _, timestamp = self._cache[key]
        if self._is_expired(timestamp):
            self.delete(key)
            return False
            
        return True
        
    def get_size(self) -> int:
        """Get current cache size in bytes."""
        return self._size

class FileCache(Cache):
    """File-based cache implementation with compression support."""
    
    def __init__(
        self,
        name: str,
        cache_dir: Union[str, Path],
        ttl: Optional[int] = None,
        max_size: Optional[int] = None,
        compress: bool = True,
        compression_level: int = 6
    ):
        """Initialize file cache with compression support."""
        super().__init__(name, ttl, max_size)
        self.cache_dir = Path(cache_dir) / name
        self.compress = compress
        self.compression_level = compression_level
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
        
    def _compress_value(self, value: Any) -> bytes:
        """Compress value using zlib."""
        import zlib
        try:
            data = pickle.dumps(value)
            if self.compress:
                return zlib.compress(data, self.compression_level)
            return data
        except Exception as e:
            raise CacheError(f"Failed to compress value: {e}")
            
    def _decompress_value(self, data: bytes) -> Any:
        """Decompress value using zlib."""
        import zlib
        try:
            if self.compress:
                data = zlib.decompress(data)
            return pickle.loads(data)
        except Exception as e:
            raise CacheError(f"Failed to decompress value: {e}")
            
    def _write_cache_file(self, path: Path, value: Any) -> int:
        """Write value to cache file and return size."""
        compressed = self._compress_value(value)
        path.write_bytes(compressed)
        return len(compressed)
        
    def _read_cache_file(self, path: Path) -> Tuple[Any, float]:
        """Read value and timestamp from cache file."""
        try:
            data = path.read_bytes()
            value = self._decompress_value(data)
            return value, path.stat().st_mtime
        except Exception as e:
            raise CacheError(f"Failed to read cache file: {e}")
            
    def _evict_if_needed(self, new_size: int) -> None:
        """Evict files if cache would exceed max size."""
        if self.max_size is None:
            return
            
        while self._size + new_size > self.max_size:
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
                    self.name
                )
            except OSError:
                break
                
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache file."""
        path = self._get_path(key)
        if not path.exists():
            return None
            
        try:
            value, timestamp = self._read_cache_file(path)
            if self.ttl and time.time() - timestamp > self.ttl:
                self.delete(key)
                return None
            return value
        except Exception as e:
            logger.error("Failed to read cache file: %s", e)
            self.delete(key)
            return None
            
    def set(self, key: str, value: Any) -> None:
        """Set value in cache file."""
        path = self._get_path(key)
        
        # Get size before writing
        try:
            compressed = self._compress_value(value)
            new_size = len(compressed)
            
            if self.max_size and new_size > self.max_size:
                raise CacheError(
                    f"Item size ({new_size} bytes) exceeds cache max size "
                    f"({self.max_size} bytes)"
                )
                
            # Remove old file size if exists
            if path.exists():
                self._size -= path.stat().st_size
                
            self._evict_if_needed(new_size)
            path.write_bytes(compressed)
            self._size += new_size
            
        except Exception as e:
            raise CacheError(f"Failed to write cache file: {e}")
            
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
        path = self._get_path(key)
        if not path.exists():
            return False
            
        if self.ttl is None:
            return True
            
        try:
            mtime = path.stat().st_mtime
            if time.time() - mtime > self.ttl:
                self.delete(key)
                return False
            return True
        except OSError:
            return False
            
    def get_size(self) -> int:
        """Get current cache size in bytes."""
        return self._size

class SQLiteCache(Cache):
    """SQLite-based cache implementation with connection pooling."""
    
    def __init__(
        self,
        name: str,
        db_path: Union[str, Path],
        ttl: Optional[int] = None,
        max_size: Optional[int] = None,
        pool_size: int = 5,
        compress: bool = True,
        compression_level: int = 6
    ):
        """Initialize SQLite cache with connection pooling."""
        super().__init__(name, ttl, max_size)
        self.db_path = Path(db_path)
        self.pool_size = pool_size
        self.compress = compress
        self.compression_level = compression_level
        self._connections: List[sqlite3.Connection] = []
        self._available_connections: List[sqlite3.Connection] = []
        self._init_db()
        
    def _init_db(self) -> None:
        """Initialize database and connection pool."""
        ensure_directory(self.db_path.parent)
        
        # Create initial connection for setup
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB,
                    size INTEGER,
                    timestamp REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)")
            
        # Initialize connection pool
        for _ in range(self.pool_size):
            conn = sqlite3.connect(
                self.db_path,
                isolation_level=None,  # Autocommit mode
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            self._connections.append(conn)
            self._available_connections.append(conn)
            
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a connection from the pool."""
        connection = None
        try:
            if not self._available_connections:
                raise CacheError("No available database connections")
                
            connection = self._available_connections.pop()
            yield connection
        finally:
            if connection:
                self._available_connections.append(connection)
                
    def _compress_value(self, value: Any) -> bytes:
        """Compress value using zlib."""
        import zlib
        try:
            data = pickle.dumps(value)
            if self.compress:
                return zlib.compress(data, self.compression_level)
            return data
        except Exception as e:
            raise CacheError(f"Failed to compress value: {e}")
            
    def _decompress_value(self, data: bytes) -> Any:
        """Decompress value using zlib."""
        import zlib
        try:
            if self.compress:
                data = zlib.decompress(data)
            return pickle.loads(data)
        except Exception as e:
            raise CacheError(f"Failed to decompress value: {e}")
            
    def _get_total_size(self) -> int:
        """Get total size of all cached items."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT SUM(size) FROM cache")
            result = cursor.fetchone()
            return result[0] or 0
            
    def _evict_if_needed(self, new_size: int) -> None:
        """Evict items if cache would exceed max size."""
        if self.max_size is None:
            return
            
        current_size = self._get_total_size()
        while current_size + new_size > self.max_size:
            with self._get_connection() as conn:
                # Get oldest item
                cursor = conn.execute(
                    "SELECT key, size FROM cache ORDER BY timestamp LIMIT 1"
                )
                row = cursor.fetchone()
                if not row:
                    break
                    
                # Delete it
                conn.execute("DELETE FROM cache WHERE key = ?", (row['key'],))
                current_size -= row['size']
                logger.debug(
                    "Evicted key %s from cache %s",
                    row['key'],
                    self.name
                )
                
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT value, timestamp FROM cache WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
                
            if self.ttl and time.time() - row['timestamp'] > self.ttl:
                self.delete(key)
                return None
                
            try:
                return self._decompress_value(row['value'])
            except Exception as e:
                logger.error("Failed to decompress value: %s", e)
                self.delete(key)
                return None
                
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        try:
            compressed = self._compress_value(value)
            new_size = len(compressed)
            
            if self.max_size and new_size > self.max_size:
                raise CacheError(
                    f"Item size ({new_size} bytes) exceeds cache max size "
                    f"({self.max_size} bytes)"
                )
                
            self._evict_if_needed(new_size)
            
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cache (key, value, size, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (key, compressed, new_size, time.time())
                )
                
        except Exception as e:
            raise CacheError(f"Failed to set cache value: {e}")
            
    def set_many(self, items: Dict[str, Any]) -> None:
        """Set multiple values in cache."""
        if not items:
            return
            
        compressed_items = []
        total_size = 0
        
        # Prepare all items
        for key, value in items.items():
            try:
                compressed = self._compress_value(value)
                size = len(compressed)
                
                if self.max_size and size > self.max_size:
                    logger.warning(
                        "Skipping item %s: size %d exceeds max size %d",
                        key, size, self.max_size
                    )
                    continue
                    
                compressed_items.append((key, compressed, size))
                total_size += size
                
            except Exception as e:
                logger.error("Failed to compress item %s: %s", key, e)
                continue
                
        if not compressed_items:
            return
            
        self._evict_if_needed(total_size)
        
        # Insert all items in a single transaction
        with self._get_connection() as conn:
            try:
                now = time.time()
                conn.execute("BEGIN TRANSACTION")
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO cache (key, value, size, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    [(k, v, s, now) for k, v, s in compressed_items]
                )
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                raise CacheError(f"Failed to set multiple cache values: {e}")
                
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            
    def delete_many(self, keys: List[str]) -> None:
        """Delete multiple values from cache."""
        if not keys:
            return
            
        with self._get_connection() as conn:
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.executemany(
                    "DELETE FROM cache WHERE key = ?",
                    [(k,) for k in keys]
                )
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                raise CacheError(f"Failed to delete multiple cache values: {e}")
                
    def clear(self) -> None:
        """Clear all values from cache."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM cache")
            
    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT timestamp FROM cache WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            
            if not row:
                return False
                
            if self.ttl and time.time() - row['timestamp'] > self.ttl:
                self.delete(key)
                return False
                
            return True
            
    def get_size(self) -> int:
        """Get current cache size in bytes."""
        return self._get_total_size()
        
    def __del__(self) -> None:
        """Close all connections on deletion."""
        for conn in self._connections:
            try:
                conn.close()
            except Exception:
                pass
