"""Tests for exception classes."""
import pytest
from bunkrr.core.exceptions import (
    BunkrrError,
    ConfigError,
    ValidationError,
    DownloadError,
    RateLimitError,
    FileSystemError,
    ScrapyError,
    HTTPError,
    ConfigVersionError,
    ShutdownError,
    ERROR_CODES
)

@pytest.mark.unit
class TestBunkrrError:
    """Test base error class functionality."""
    
    def test_basic_error(self):
        """Test basic error creation and string representation."""
        error = BunkrrError("Test message")
        assert str(error) == "Test message"
        assert error.message == "Test message"
        assert error.details is None
        
    def test_error_with_details(self):
        """Test error with additional details."""
        error = BunkrrError("Test message", details="Extra info")
        assert str(error) == "Test message - Extra info"
        assert error.message == "Test message"
        assert error.details == "Extra info"
        
    def test_to_dict(self):
        """Test conversion to dictionary format."""
        error = BunkrrError("Test message", details="Extra info")
        error_dict = error.to_dict()
        
        assert error_dict['type'] == 'BunkrrError'
        assert error_dict['message'] == 'Test message'
        assert error_dict['details'] == 'Extra info'

@pytest.mark.unit
class TestSpecializedErrors:
    """Test specialized error classes."""
    
    def test_download_error(self):
        """Test DownloadError functionality."""
        error = DownloadError(
            message="Download failed",
            url="https://example.com",
            status_code=404,
            details="Not found"
        )
        
        assert str(error) == "Download failed - Not found"
        error_dict = error.to_dict()
        assert error_dict['url'] == 'https://example.com'
        assert error_dict['status_code'] == 404
        
    def test_filesystem_error(self):
        """Test FileSystemError functionality."""
        error = FileSystemError(
            message="File operation failed",
            path="/path/to/file",
            operation="write",
            details="Permission denied"
        )
        
        assert str(error) == "File operation failed - Permission denied"
        error_dict = error.to_dict()
        assert error_dict['path'] == '/path/to/file'
        assert error_dict['operation'] == 'write'
        
    def test_scrapy_error(self):
        """Test ScrapyError functionality."""
        error = ScrapyError(
            message="Spider failed",
            spider_name="test_spider",
            url="https://example.com",
            details="Connection timeout"
        )
        
        assert str(error) == "Spider failed - Connection timeout"
        error_dict = error.to_dict()
        assert error_dict['spider_name'] == 'test_spider'
        assert error_dict['url'] == 'https://example.com'
        
    def test_http_error(self):
        """Test HTTPError functionality."""
        error = HTTPError(
            message="Request failed",
            url="https://example.com",
            method="GET",
            status_code=500,
            details="Server error"
        )
        
        assert str(error) == "Request failed - Server error"
        error_dict = error.to_dict()
        assert error_dict['url'] == 'https://example.com'
        assert error_dict['method'] == 'GET'
        assert error_dict['status_code'] == 500

@pytest.mark.unit
class TestErrorCodes:
    """Test error code mapping."""
    
    def test_error_code_mapping(self):
        """Test error code mappings."""
        assert ERROR_CODES[ConfigError] == 'CONFIG_ERROR'
        assert ERROR_CODES[ValidationError] == 'VALIDATION_ERROR'
        assert ERROR_CODES[DownloadError] == 'DOWNLOAD_ERROR'
        assert ERROR_CODES[RateLimitError] == 'RATE_LIMIT_ERROR'
        assert ERROR_CODES[FileSystemError] == 'FILESYSTEM_ERROR'
        assert ERROR_CODES[ScrapyError] == 'SCRAPY_ERROR'
        assert ERROR_CODES[HTTPError] == 'HTTP_ERROR'
        
    def test_error_inheritance(self):
        """Test error class inheritance."""
        assert issubclass(ConfigVersionError, ConfigError)
        assert issubclass(ConfigError, BunkrrError)
        assert issubclass(ValidationError, BunkrrError)
        assert issubclass(ShutdownError, BunkrrError) 
