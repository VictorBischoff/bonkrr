"""Tests for URL validation and user input handling."""
import pytest
from pathlib import Path
from unittest.mock import patch

from bunkrr.user_input import URLValidator, URLValidationResult, InputHandler
from bunkrr.config import DownloadConfig

@pytest.fixture
def validator():
    """Create a URLValidator instance with test configuration."""
    config = DownloadConfig()
    return URLValidator(config)

def test_valid_urls(validator):
    """Test validation of valid URLs."""
    valid_urls = [
        'https://bunkr.site/a/abc123',
        'https://bunkr.ru/album/def456',
        'https://media-files.bunkr.site/f/ghi789',
        'https://i-burger.bunkr.ru/v/jkl012',
        'bunkr.site/a/mno345',  # No protocol
        'https://www.bunkr.site/a/pqr678',  # With www
        'https://cdn.bunkr.site/f/stu901',  # CDN subdomain
        'https://bunkr.site/a/xyz234/my-album',  # With title
    ]

    for url in valid_urls:
        result = validator.validate(url)
        assert result.is_valid, f"URL should be valid: {url}"
        assert result.normalized_url is not None
        assert result.error_message is None

def test_invalid_urls(validator):
    """Test validation of invalid URLs."""
    invalid_urls = [
        ('', 'Invalid URL format'),
        ('not-a-url', 'Invalid URL format'),
        ('https://example.com', 'Not a valid Bunkr domain'),
        ('https://bunkr.invalid/a/123', 'Not a valid Bunkr domain'),
        ('https://bunkr.site/invalid/123', "URL doesn't match expected Bunkr format"),
        ('https://bunkr.site/a/', "URL doesn't match expected Bunkr format"),
        ('https://bunkr.site/a/ab', 'Invalid ID format'),  # ID too short
        ('https://invalid-sub.bunkr.site/a/123', 'Invalid subdomain'),
    ]

    for url, expected_error in invalid_urls:
        result = validator.validate(url)
        assert not result.is_valid, f"URL should be invalid: {url}"
        assert result.normalized_url is None
        assert result.error_message == expected_error

def test_url_normalization(validator):
    """Test URL normalization."""
    test_cases = [
        (
            'https://bunkr.site/a/abc123/my-album',
            'https://bunkr.site/a/abc123'
        ),
        (
            'bunkr.site/album/def456',
            'https://bunkr.site/album/def456'
        ),
        (
            'https://www.bunkr.site/f/ghi789/',
            'https://www.bunkr.site/f/ghi789'
        ),
    ]

    for input_url, expected_url in test_cases:
        result = validator.validate(input_url)
        assert result.is_valid
        assert result.normalized_url == expected_url

def test_validation_caching(validator):
    """Test that validation results are cached."""
    url = 'https://bunkr.site/a/abc123'
    
    # First validation
    result1 = validator.validate(url)
    assert result1.is_valid
    
    # Second validation (should use cache)
    result2 = validator.validate(url)
    assert result2.is_valid
    assert result1.normalized_url == result2.normalized_url

def test_input_handler_url_validation():
    """Test URL validation in InputHandler."""
    handler = InputHandler()
    
    # Test valid URLs
    urls = [
        'https://bunkr.site/a/abc123',
        'https://bunkr.ru/album/def456',
        'invalid-url',  # This one should be skipped
        'https://bunkr.site/f/ghi789'
    ]
    
    valid_urls = handler._validate_urls(urls)
    assert len(valid_urls) == 3  # Should have 3 valid URLs
    assert all(url.startswith('https://') for url in valid_urls)

@patch('rich.prompt.Prompt.ask')
def test_input_handler_download_folder(mock_ask):
    """Test download folder creation and validation."""
    handler = InputHandler()
    test_path = Path('test_downloads')
    mock_ask.return_value = str(test_path)
    
    try:
        # Test folder creation
        folder = handler.get_download_folder()
        assert folder.exists()
        assert folder.is_dir()
        assert folder == test_path
        
    finally:
        # Cleanup
        if test_path.exists():
            test_path.rmdir()

def test_empty_url_list():
    """Test handling of empty URL list."""
    handler = InputHandler()
    assert handler._validate_urls([]) == []
    assert handler._validate_urls(['', ' ', '\n']) == [] 
