"""Tests for error handling system."""
import pytest
from typing import Dict, Any

from bunkrr.core.error_handler import ErrorHandler, handle_errors, handle_async_errors
from bunkrr.core.exceptions import (
    BunkrrError,
    ValidationError,
    DownloadError,
    ConfigError
)

@pytest.mark.unit
class TestErrorHandler:
    """Test error handler functionality."""
    
    def test_handle_error_basic(self):
        """Test basic error handling."""
        error = ValueError("Test error")
        error_info = ErrorHandler.handle_error(error, "test", reraise=False)
        
        assert error_info['type'] == 'ValueError'
        assert error_info['message'] == 'Test error'
        assert error_info['error_code'] == 'UNKNOWN_ERROR'
        assert error_info['context'] == 'test'
        assert 'traceback' in error_info
        
    def test_handle_bunkrr_error(self):
        """Test handling of BunkrrError instances."""
        error = ValidationError("Invalid input", details="Value too large")
        error_info = ErrorHandler.handle_error(error, "validation", reraise=False)
        
        assert error_info['type'] == 'ValidationError'
        assert error_info['message'] == 'Invalid input'
        assert error_info['details'] == 'Value too large'
        assert error_info['error_code'] == 'VALIDATION_ERROR'
        assert error_info['context'] == 'validation'
        
    def test_error_reraising(self):
        """Test error reraising behavior."""
        error = ConfigError("Bad config")
        
        with pytest.raises(ConfigError) as exc_info:
            ErrorHandler.handle_error(error, "config", reraise=True)
            
        assert str(exc_info.value) == "Bad config"
        
    def test_error_info_creation(self):
        """Test error info dictionary creation."""
        error = DownloadError(
            message="Download failed",
            url="https://example.com",
            status_code=404
        )
        error_info = ErrorHandler._create_error_info(error, "download")
        
        assert error_info['type'] == 'DownloadError'
        assert error_info['message'] == 'Download failed'
        assert error_info['url'] == 'https://example.com'
        assert error_info['status_code'] == 404
        assert error_info['context'] == 'download'

@pytest.mark.unit
class TestErrorDecorators:
    """Test error handling decorators."""
    
    def test_handle_errors_decorator(self):
        """Test synchronous error handling decorator."""
        @handle_errors(target_error=ValidationError, context="validation")
        def validate(value: int) -> bool:
            if value < 0:
                raise ValueError("Value must be positive")
            return True
            
        # Test successful case
        assert validate(5) is True
        
        # Test error case
        with pytest.raises(ValidationError) as exc_info:
            validate(-1)
        assert "Value must be positive" in str(exc_info.value)
        
    def test_handle_errors_no_reraise(self):
        """Test error handling without reraising."""
        @handle_errors(target_error=ValidationError, context="test", reraise=False)
        def might_fail() -> str:
            raise ValueError("Oops")
            
        assert might_fail() is None
        
    @pytest.mark.async_
    async def test_handle_async_errors(self):
        """Test asynchronous error handling decorator."""
        @handle_async_errors(target_error=DownloadError, context="download")
        async def download(url: str) -> Dict[str, Any]:
            if not url.startswith('http'):
                raise ValueError("Invalid URL")
            return {'url': url, 'status': 'success'}
            
        # Test successful case
        result = await download('https://example.com')
        assert result['status'] == 'success'
        
        # Test error case
        with pytest.raises(DownloadError) as exc_info:
            await download('invalid-url')
        assert "Invalid URL" in str(exc_info.value)
        
    def test_nested_error_handling(self):
        """Test nested error handling behavior."""
        @handle_errors(target_error=ConfigError, context="outer")
        def outer_function():
            return inner_function()
            
        @handle_errors(target_error=ValidationError, context="inner")
        def inner_function():
            raise ValueError("Inner error")
            
        with pytest.raises(ValidationError) as exc_info:
            outer_function()
        assert "Inner error" in str(exc_info.value) 
