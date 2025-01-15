"""Test media utilities."""
import pytest
from pathlib import Path

from bunkrr.core.exceptions import ValidationError
from bunkrr.utils.media import (
    get_media_type,
    is_media_file,
    extract_filename,
    calculate_file_hash,
    verify_file_integrity,
    clean_failed_downloads,
    get_media_info,
    MEDIA_EXTENSIONS
)

def test_get_media_type():
    """Test media type detection."""
    test_cases = [
        # Images
        ("test.jpg", "image"),
        ("test.jpeg", "image"),
        ("test.png", "image"),
        ("test.gif", "image"),
        ("test.webp", "image"),
        # Videos
        ("test.mp4", "video"),
        ("test.webm", "video"),
        ("test.mkv", "video"),
        # Archives
        ("test.zip", "application"),
        ("test.rar", "application"),
        ("test.7z", "application"),
        # Invalid
        ("test.txt", None),
        ("test", None),
        ("", None)
    ]
    
    for filename, expected_type in test_cases:
        assert get_media_type(filename) == expected_type

def test_is_media_file():
    """Test media file detection."""
    # Test valid media files
    for ext in MEDIA_EXTENSIONS:
        assert is_media_file(f"test{ext}")
    
    # Test invalid files
    invalid_files = [
        "test.txt",
        "test.doc",
        "test",
        "",
        "test.jpg.txt"
    ]
    
    for filename in invalid_files:
        assert not is_media_file(filename)

def test_extract_filename():
    """Test filename extraction from URL."""
    test_cases = [
        # Valid URLs
        ("https://example.com/test.jpg", "test.jpg"),
        ("https://example.com/path/video.mp4", "video.mp4"),
        ("https://example.com/file%20with%20spaces.png", "file with spaces.png"),
        # Invalid URLs
        ("https://example.com/", None),
        ("https://example.com/test.txt", None),
        ("invalid_url", None),
        ("", None)
    ]
    
    for url, expected in test_cases:
        assert extract_filename(url) == expected

def test_calculate_file_hash(tmp_path):
    """Test file hash calculation."""
    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    
    # Test SHA256 hash
    sha256_hash = calculate_file_hash(test_file, "sha256")
    assert isinstance(sha256_hash, str)
    assert len(sha256_hash) == 64  # SHA256 produces 64 char hex string
    
    # Test non-existent file
    assert calculate_file_hash(tmp_path / "nonexistent") is None
    
    # Test directory
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    assert calculate_file_hash(test_dir) is None

def test_verify_file_integrity(tmp_path):
    """Test file integrity verification."""
    # Create test file
    test_file = tmp_path / "test.txt"
    content = b"test content"
    test_file.write_bytes(content)
    
    # Calculate hash
    file_hash = calculate_file_hash(test_file)
    
    # Test valid file
    is_valid, error = verify_file_integrity(
        test_file,
        expected_size=len(content),
        expected_hash=file_hash
    )
    assert is_valid
    assert error is None
    
    # Test size mismatch
    is_valid, error = verify_file_integrity(
        test_file,
        expected_size=len(content) + 1
    )
    assert not is_valid
    assert "size" in error.lower()
    
    # Test hash mismatch
    is_valid, error = verify_file_integrity(
        test_file,
        expected_hash="invalid_hash"
    )
    assert not is_valid
    assert "hash" in error.lower()
    
    # Test non-existent file
    is_valid, error = verify_file_integrity(tmp_path / "nonexistent")
    assert not is_valid
    assert "exist" in error.lower()

def test_clean_failed_downloads(tmp_path):
    """Test cleanup of failed downloads."""
    # Create test files
    temp_file = tmp_path / "test.tmp"
    temp_file.touch()
    
    empty_file = tmp_path / "empty.jpg"
    empty_file.touch()
    
    valid_file = tmp_path / "valid.jpg"
    valid_file.write_text("content")
    
    # Clean up
    clean_failed_downloads(temp_file)
    clean_failed_downloads(empty_file)
    clean_failed_downloads(valid_file)
    
    # Verify
    assert not temp_file.exists()
    assert not empty_file.exists()
    assert valid_file.exists()

def test_get_media_info(tmp_path):
    """Test media file information retrieval."""
    # Create test file
    test_file = tmp_path / "test.jpg"
    test_file.write_text("test content")
    
    # Get info
    info = get_media_info(test_file)
    
    # Verify info
    assert isinstance(info, dict)
    assert info["path"] == str(test_file)
    assert info["size"] == len("test content")
    assert info["type"] == "image"
    assert "modified" in info
    assert "hash" in info
    
    # Test non-existent file
    with pytest.raises(ValidationError):
        get_media_info(tmp_path / "nonexistent") 
