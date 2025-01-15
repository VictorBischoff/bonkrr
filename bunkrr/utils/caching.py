"""Caching utilities for the bunkrr package."""
import json
import os
import pickle
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Set, Tuple, Union

from ..core.exceptions import BunkrrError
from ..core.logger import setup_logger
from .filesystem import ensure_directory

logger = setup_logger('bunkrr.caching')

class Cache:
    """Base class for caching implementations."""
    
    def __init__(self, name: str, ttl: Optional[int] = None):
        """Initialize cache with name and TTL in seconds."""
        self.name = name
        self.ttl = ttl
    
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

class MemoryCache(Cache):
    """In-memory cache implementation."""
    
    def __init__(self, name: str, ttl: Optional[int] = None):
        """Initialize memory cache."""
        super().__init__(name, ttl)
        self._cache: Dict[str, Tuple[Any, float]] = {}
    
    def _is_expired(self, timestamp: float) -> bool:
        """Check if cache entry is expired."""
        if self.ttl is None:
            return False
        return time.time() - timestamp > self.ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key not in self._cache:
            return None
            
        value, timestamp = self._cache[key]
        if self._is_expired(timestamp):
            del self._cache[key]
            return None
            
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        self._cache[key] = (value, time.time())
    
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        self._cache.pop(key, None)
    
    def clear(self) -> None:
        """Clear all values from cache."""
        self._cache.clear()
    
    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        if key not in self._cache:
            return False
            
        _, timestamp = self._cache[key]
        if self._is_expired(timestamp):
            del self._cache[key]
            return False
            
        return True

class FileCache(Cache):
    """File-based cache implementation."""
    
    def __init__(
        self,
        name: str,
        cache_dir: Optional[Union[str, Path]] = None,
        ttl: Optional[int] = None
    ):
        """Initialize file cache."""
        super().__init__(name, ttl)
        
        # Set up cache directory
        if cache_dir is None:
            cache_dir = Path.home() / '.bunkrr' / 'cache'
        self.cache_dir = Path(cache_dir) / name
        ensure_directory(self.cache_dir)
        
        logger.debug("Initialized file cache at %s", self.cache_dir)
    
    def _get_path(self, key: str) -> Path:
        """Get cache file path for key."""
        # Use first 2 chars of key as subdirectory
        subdir = self.cache_dir / key[:2]
        ensure_directory(subdir)
        return subdir / f"{key[2:]}.cache"
    
    def _is_expired(self, path: Path) -> bool:
        """Check if cache file is expired."""
        if self.ttl is None:
            return False
            
        try:
            mtime = path.stat().st_mtime
            return time.time() - mtime > self.ttl
        except OSError:
            return True
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache file."""
        path = self._get_path(key)
        
        if not path.is_file():
            return None
            
        if self._is_expired(path):
            path.unlink()
            return None
            
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.error("Failed to read cache file %s: %s", path, str(e))
            return None
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache file."""
        path = self._get_path(key)
        
        try:
            with open(path, 'wb') as f:
                pickle.dump(value, f)
        except Exception as e:
            logger.error("Failed to write cache file %s: %s", path, str(e))
    
    def delete(self, key: str) -> None:
        """Delete cache file."""
        path = self._get_path(key)
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.error("Failed to delete cache file %s: %s", path, str(e))
    
    def clear(self) -> None:
        """Clear all cache files."""
        try:
            for path in self.cache_dir.glob("**/*.cache"):
                path.unlink()
        except Exception as e:
            logger.error("Failed to clear cache directory %s: %s", self.cache_dir, str(e))
    
    def has(self, key: str) -> bool:
        """Check if cache file exists and is not expired."""
        path = self._get_path(key)
        return path.is_file() and not self._is_expired(path)

class SQLiteCache(Cache):
    """SQLite-based cache implementation."""
    
    def __init__(
        self,
        name: str,
        db_path: Optional[Union[str, Path]] = None,
        ttl: Optional[int] = None
    ):
        """Initialize SQLite cache."""
        super().__init__(name, ttl)
        
        # Set up database
        if db_path is None:
            db_path = Path.home() / '.bunkrr' / 'cache' / 'cache.db'
        self.db_path = Path(db_path)
        ensure_directory(self.db_path.parent)
        
        self._init_db()
        logger.debug("Initialized SQLite cache at %s", self.db_path)
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    namespace TEXT,
                    key TEXT,
                    value BLOB,
                    timestamp REAL,
                    PRIMARY KEY (namespace, key)
                )
            """)
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT value, timestamp FROM cache WHERE namespace = ? AND key = ?",
                (self.name, key)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
                
            value, timestamp = row
            
            if self.ttl and time.time() - timestamp > self.ttl:
                self.delete(key)
                return None
                
            try:
                return pickle.loads(value)
            except Exception as e:
                logger.error("Failed to deserialize cache value: %s", str(e))
                return None
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        try:
            serialized = pickle.dumps(value)
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cache (namespace, key, value, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (self.name, key, serialized, time.time())
                )
        except Exception as e:
            logger.error("Failed to set cache value: %s", str(e))
    
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM cache WHERE namespace = ? AND key = ?",
                (self.name, key)
            )
    
    def clear(self) -> None:
        """Clear all values from cache."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM cache WHERE namespace = ?",
                (self.name,)
            )
    
    def has(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT timestamp FROM cache WHERE namespace = ? AND key = ?",
                (self.name, key)
            )
            row = cursor.fetchone()
            
            if not row:
                return False
                
            if self.ttl and time.time() - row[0] > self.ttl:
                self.delete(key)
                return False
                
            return True
