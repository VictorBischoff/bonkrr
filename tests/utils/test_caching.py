"""Test caching utilities."""
import time
import pytest
from pathlib import Path

from bunkrr.utils.caching import (
    MemoryCache,
    FileCache,
    SQLiteCache
)

def test_memory_cache():
    """Test memory cache implementation."""
    cache = MemoryCache("test", ttl=1)
    
    # Test basic operations
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    assert cache.has("key1")
    
    # Test non-existent key
    assert cache.get("nonexistent") is None
    assert not cache.has("nonexistent")
    
    # Test deletion
    cache.delete("key1")
    assert cache.get("key1") is None
    assert not cache.has("key1")
    
    # Test TTL expiration
    cache.set("key2", "value2")
    time.sleep(1.1)  # Wait for TTL to expire
    assert cache.get("key2") is None
    assert not cache.has("key2")
    
    # Test clear
    cache.set("key3", "value3")
    cache.clear()
    assert cache.get("key3") is None

def test_file_cache(tmp_path):
    """Test file cache implementation."""
    cache_dir = tmp_path / "cache"
    cache = FileCache("test", cache_dir=cache_dir, ttl=1)
    
    # Test basic operations
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    assert cache.has("key1")
    
    # Test non-existent key
    assert cache.get("nonexistent") is None
    assert not cache.has("nonexistent")
    
    # Test deletion
    cache.delete("key1")
    assert cache.get("key1") is None
    assert not cache.has("key1")
    
    # Test TTL expiration
    cache.set("key2", "value2")
    time.sleep(1.1)  # Wait for TTL to expire
    assert cache.get("key2") is None
    assert not cache.has("key2")
    
    # Test clear
    cache.set("key3", "value3")
    cache.clear()
    assert cache.get("key3") is None
    
    # Test complex objects
    data = {"test": [1, 2, 3], "nested": {"a": "b"}}
    cache.set("complex", data)
    assert cache.get("complex") == data

def test_sqlite_cache(tmp_path):
    """Test SQLite cache implementation."""
    db_path = tmp_path / "cache.db"
    cache = SQLiteCache("test", db_path=db_path, ttl=1)
    
    # Test basic operations
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    assert cache.has("key1")
    
    # Test non-existent key
    assert cache.get("nonexistent") is None
    assert not cache.has("nonexistent")
    
    # Test deletion
    cache.delete("key1")
    assert cache.get("key1") is None
    assert not cache.has("key1")
    
    # Test TTL expiration
    cache.set("key2", "value2")
    time.sleep(1.1)  # Wait for TTL to expire
    assert cache.get("key2") is None
    assert not cache.has("key2")
    
    # Test clear
    cache.set("key3", "value3")
    cache.clear()
    assert cache.get("key3") is None
    
    # Test multiple namespaces
    cache2 = SQLiteCache("test2", db_path=db_path)
    cache.set("shared_key", "value1")
    cache2.set("shared_key", "value2")
    assert cache.get("shared_key") == "value1"
    assert cache2.get("shared_key") == "value2"

@pytest.mark.parametrize("cache_class,cache_args", [
    (MemoryCache, {"name": "test"}),
    (FileCache, {"name": "test", "cache_dir": "tmp_cache"}),
    (SQLiteCache, {"name": "test", "db_path": "tmp_cache.db"})
])
def test_cache_interface(tmp_path, cache_class, cache_args):
    """Test cache interface consistency."""
    if "cache_dir" in cache_args:
        cache_args["cache_dir"] = tmp_path / cache_args["cache_dir"]
    if "db_path" in cache_args:
        cache_args["db_path"] = tmp_path / cache_args["db_path"]
    
    cache = cache_class(**cache_args)
    
    # Test basic operations
    cache.set("test_key", "test_value")
    assert cache.get("test_key") == "test_value"
    assert cache.has("test_key")
    
    cache.delete("test_key")
    assert not cache.has("test_key")
    assert cache.get("test_key") is None
    
    # Test clear
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.clear()
    assert not cache.has("key1")
    assert not cache.has("key2") 
