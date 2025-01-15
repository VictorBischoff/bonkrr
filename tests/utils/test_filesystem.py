"""Test filesystem utilities."""
import os
import pytest
from pathlib import Path

from bunkrr.core.exceptions import FileSystemError
from bunkrr.utils.filesystem import (
    ensure_directory,
    sanitize_filename,
    get_unique_path,
    safe_move,
    safe_remove,
    get_file_size,
    is_valid_path
)

def test_ensure_directory(tmp_path):
    """Test directory creation and validation."""
    # Test creating new directory
    test_dir = tmp_path / "test_dir"
    ensure_directory(test_dir)
    assert test_dir.is_dir()
    
    # Test existing directory
    ensure_directory(test_dir)  # Should not raise
    
    # Test nested directory
    nested_dir = test_dir / "nested" / "dir"
    ensure_directory(nested_dir)
    assert nested_dir.is_dir()
    
    # Test non-writable directory
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o444)  # Read-only
    
    with pytest.raises(FileSystemError):
        ensure_directory(readonly_dir / "subdir")

def test_sanitize_filename():
    """Test filename sanitization."""
    test_cases = [
        ("test.txt", "test.txt"),  # Normal case
        ("test/file.txt", "testfile.txt"),  # Remove path separator
        ("test..txt", "test.txt"),  # Remove extra dots
        ("", "unnamed"),  # Empty filename
        ("test!@#$%^&*.txt", "test.txt"),  # Remove special chars
        ("a" * 300 + ".txt", "a" * 251 + ".txt"),  # Truncate long name
        (" test .txt ", "test.txt"),  # Trim spaces
        ("../test.txt", "test.txt"),  # Remove path traversal
    ]
    
    for input_name, expected in test_cases:
        assert sanitize_filename(input_name) == expected

def test_get_unique_path(tmp_path):
    """Test unique path generation."""
    # Test non-existent path
    test_path = tmp_path / "test.txt"
    assert get_unique_path(test_path) == test_path
    
    # Test existing file
    test_path.touch()
    unique_path = get_unique_path(test_path)
    assert unique_path != test_path
    assert unique_path.name.startswith("test_")
    assert unique_path.suffix == ".txt"
    
    # Test multiple existing files
    unique_path.touch()
    another_path = get_unique_path(test_path)
    assert another_path != test_path
    assert another_path != unique_path
    
    # Test directory
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    unique_dir = get_unique_path(test_dir)
    assert unique_dir != test_dir
    assert unique_dir.name.startswith("test_dir_")

def test_safe_move(tmp_path):
    """Test safe file moving."""
    # Create source file
    src = tmp_path / "source.txt"
    src.write_text("test content")
    
    # Test basic move
    dst = tmp_path / "dest.txt"
    safe_move(src, dst)
    assert not src.exists()
    assert dst.exists()
    assert dst.read_text() == "test content"
    
    # Test move to existing file
    src2 = tmp_path / "source2.txt"
    src2.write_text("new content")
    safe_move(src2, dst)  # Should create unique name
    assert not src2.exists()
    assert len(list(tmp_path.glob("dest*.txt"))) == 2
    
    # Test move to non-existent directory
    src3 = tmp_path / "source3.txt"
    src3.write_text("test")
    dst3 = tmp_path / "subdir" / "dest3.txt"
    safe_move(src3, dst3)
    assert dst3.exists()
    assert dst3.read_text() == "test"

def test_safe_remove(tmp_path):
    """Test safe file removal."""
    # Test existing file
    test_file = tmp_path / "test.txt"
    test_file.touch()
    safe_remove(test_file)
    assert not test_file.exists()
    
    # Test non-existent file
    safe_remove(test_file)  # Should not raise
    
    # Test directory (should not remove)
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    safe_remove(test_dir)
    assert test_dir.exists()

def test_get_file_size(tmp_path):
    """Test file size retrieval."""
    # Test existing file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    assert get_file_size(test_file) == len("test content")
    
    # Test non-existent file
    assert get_file_size(tmp_path / "nonexistent.txt") is None
    
    # Test directory
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    assert get_file_size(test_dir) is not None  # Directory size

def test_is_valid_path(tmp_path):
    """Test path validation."""
    # Test writable directory
    assert is_valid_path(tmp_path)
    
    # Test non-existent path
    assert is_valid_path(tmp_path / "nonexistent")
    
    # Test non-writable directory
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o444)  # Read-only
    assert not is_valid_path(readonly_dir / "test.txt")
    
    # Test file in writable directory
    test_file = tmp_path / "test.txt"
    test_file.touch()
    assert is_valid_path(test_file)
    
    # Test file in non-writable directory
    readonly_file = readonly_dir / "test.txt"
    assert not is_valid_path(readonly_file) 
