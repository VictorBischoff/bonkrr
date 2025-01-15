"""Test input utilities."""
import pytest
from pathlib import Path

from bunkrr.core.exceptions import ValidationError
from bunkrr.utils.input import (
    parse_urls,
    parse_path,
    parse_bool,
    parse_int,
    parse_float,
    parse_choice,
    parse_key_value
)

def test_parse_urls():
    """Test URL parsing."""
    # Test valid URLs
    input_text = """
    https://bunkr.site/a/test1
    https://bunkr.ru/v/test2.mp4,https://bunkr.is/f/test3
    https://bunkr.to/a/test4; https://bunkr.fi/v/test5
    """
    
    urls = parse_urls(input_text)
    assert len(urls) == 5
    assert all(url.startswith("https://") for url in urls)
    
    # Test invalid URLs
    input_text = """
    https://bunkr.site/a/test1
    invalid_url
    https://example.com/test
    """
    
    urls = parse_urls(input_text)
    assert len(urls) == 1
    assert urls[0] == "https://bunkr.site/a/test1"
    
    # Test empty input
    assert parse_urls("") == []
    assert parse_urls("   ") == []

def test_parse_path(tmp_path):
    """Test path parsing."""
    # Test valid path
    path = parse_path(str(tmp_path))
    assert path == tmp_path
    assert path.is_dir()
    
    # Test path creation
    new_path = tmp_path / "new_dir"
    path = parse_path(str(new_path), create=True)
    assert path.exists()
    assert path.is_dir()
    
    # Test must_exist validation
    with pytest.raises(ValidationError):
        parse_path(str(tmp_path / "nonexistent"), must_exist=True)
    
    # Test non-writable path
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o444)  # Read-only
    
    with pytest.raises(ValidationError):
        parse_path(str(readonly_dir / "test"))
    
    # Test path expansion
    home_path = parse_path("~/test")
    assert str(home_path).startswith(str(Path.home()))

def test_parse_bool():
    """Test boolean parsing."""
    # Test true values
    true_values = ["1", "true", "yes", "y", "on", "TRUE", "YES"]
    for value in true_values:
        assert parse_bool(value) is True
    
    # Test false values
    false_values = ["0", "false", "no", "n", "off", "FALSE", "NO"]
    for value in false_values:
        assert parse_bool(value) is False
    
    # Test invalid values
    invalid_values = ["", "maybe", "2", "invalid"]
    for value in invalid_values:
        with pytest.raises(ValidationError):
            parse_bool(value)

def test_parse_int():
    """Test integer parsing."""
    # Test valid integers
    assert parse_int("123") == 123
    assert parse_int("-456") == -456
    assert parse_int("0") == 0
    
    # Test range validation
    assert parse_int("5", min_val=0, max_val=10) == 5
    
    with pytest.raises(ValidationError):
        parse_int("5", min_val=10)
    
    with pytest.raises(ValidationError):
        parse_int("15", max_val=10)
    
    # Test invalid values
    invalid_values = ["", "abc", "1.23", "1e5"]
    for value in invalid_values:
        with pytest.raises(ValidationError):
            parse_int(value)

def test_parse_float():
    """Test float parsing."""
    # Test valid floats
    assert parse_float("123.45") == 123.45
    assert parse_float("-456.78") == -456.78
    assert parse_float("0.0") == 0.0
    assert parse_float("1e-10") == 1e-10
    
    # Test range validation
    assert parse_float("5.5", min_val=0, max_val=10) == 5.5
    
    with pytest.raises(ValidationError):
        parse_float("5.5", min_val=10)
    
    with pytest.raises(ValidationError):
        parse_float("15.5", max_val=10)
    
    # Test invalid values
    invalid_values = ["", "abc", "12.34.56"]
    for value in invalid_values:
        with pytest.raises(ValidationError):
            parse_float(value)

def test_parse_choice():
    """Test choice parsing."""
    choices = {"red", "green", "blue"}
    
    # Test valid choices
    assert parse_choice("red", choices) == "red"
    assert parse_choice("RED", choices, case_sensitive=False) == "red"
    
    # Test invalid choices
    with pytest.raises(ValidationError):
        parse_choice("yellow", choices)
    
    with pytest.raises(ValidationError):
        parse_choice("RED", choices, case_sensitive=True)
    
    # Test empty choice
    with pytest.raises(ValidationError):
        parse_choice("", choices)

def test_parse_key_value():
    """Test key-value parsing."""
    # Test valid key-value pairs
    assert parse_key_value("key=value") == ("key", "value")
    assert parse_key_value("key=") == ("key", "")
    assert parse_key_value("key=value with spaces") == ("key", "value with spaces")
    
    # Test invalid formats
    invalid_formats = [
        "",  # Empty string
        "key",  # Missing equals
        "=value",  # Empty key
        "key=value=extra"  # Multiple equals
    ]
    
    for value in invalid_formats:
        with pytest.raises(ValidationError):
            parse_key_value(value) 
