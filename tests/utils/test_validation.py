"""Test validation utilities."""
import pytest
from pathlib import Path

from bunkrr.core.exceptions import ValidationError
from bunkrr.utils.validation import (
    URLValidator,
    validate_download_path,
    validate_config_value,
    url_validator
)

def test_url_validator():
    """Test URL validation."""
    validator = URLValidator()
    
    # Test valid URLs
    valid_urls = [
        "https://bunkr.site/a/IwmsU",
        "https://bunkr.ru/v/testfile-Yt5Vb.mp4",
        "https://cdn.bunkr.is/f/abc123",
        "https://i-burger.bunkr.ru/v/test-123.mp4",
        "https://media-files.bunkr.to/a/xyz789"
    ]
    
    for url in valid_urls:
        assert validator.is_valid_url(url)
        validator.validate_url(url)  # Should not raise
    
    # Test invalid URLs
    invalid_urls = [
        "",  # Empty
        "not_a_url",  # Not a URL
        "http://example.com",  # Wrong domain
        "https://bunkr.com/test",  # Wrong TLD
        "https://invalid.bunkr.site/a/test",  # Invalid subdomain
        "https://bunkr.site/invalid/test",  # Invalid path
        "https://bunkr.site/a/test!@#$",  # Invalid characters
        "https://bunkr.site/a/" + "x" * 50  # Too long
    ]
    
    for url in invalid_urls:
        assert not validator.is_valid_url(url)
        with pytest.raises(ValidationError):
            validator.validate_url(url)

def test_validate_urls():
    """Test multiple URL validation."""
    validator = URLValidator()
    
    # Test valid URL list
    valid_urls = [
        "https://bunkr.site/a/test1",
        "https://bunkr.ru/v/test2.mp4"
    ]
    validator.validate_urls(valid_urls)  # Should not raise
    
    # Test empty list
    with pytest.raises(ValidationError):
        validator.validate_urls([])
    
    # Test list with invalid URL
    invalid_urls = [
        "https://bunkr.site/a/test1",
        "invalid_url"
    ]
    with pytest.raises(ValidationError):
        validator.validate_urls(invalid_urls)

def test_validate_download_path(tmp_path):
    """Test download path validation."""
    # Test valid path
    valid_path = tmp_path / "downloads"
    validate_download_path(valid_path)  # Should not raise
    
    # Test None path
    with pytest.raises(ValidationError):
        validate_download_path(None)
    
    # Test non-writable path (simulate by creating readonly dir)
    readonly_path = tmp_path / "readonly"
    readonly_path.mkdir()
    readonly_path.chmod(0o444)  # Read-only
    
    with pytest.raises(ValidationError):
        validate_download_path(readonly_path)

def test_validate_config_value():
    """Test configuration value validation."""
    # Test valid values
    validate_config_value("test", 5, min_val=0, max_val=10)  # Should not raise
    validate_config_value("test", "value")  # Should not raise
    
    # Test None value
    with pytest.raises(ValidationError):
        validate_config_value("test", None)
    
    # Test value below minimum
    with pytest.raises(ValidationError):
        validate_config_value("test", 5, min_val=10)
    
    # Test value above maximum
    with pytest.raises(ValidationError):
        validate_config_value("test", 15, max_val=10)

def test_global_url_validator():
    """Test global URL validator instance."""
    # Test that global instance works
    assert url_validator.is_valid_url("https://bunkr.site/a/test")
    with pytest.raises(ValidationError):
        url_validator.validate_url("invalid_url") 
