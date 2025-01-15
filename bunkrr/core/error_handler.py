"""Error handling utilities for the bunkrr package.

This module provides centralized error handling functionality for the Bunkrr application.
It includes decorators and utilities for consistent error handling across both synchronous
and asynchronous code.

Key Components:
    - ErrorHandler: Central error handling class
    - handle_errors: Decorator for synchronous functions
    - handle_async_errors: Decorator for asynchronous functions

Example Usage:
    >>> from bunkrr.core.error_handler import handle_errors
    >>> from bunkrr.core.exceptions import ValidationError
    >>>
    >>> @handle_errors(target_error=ValidationError, context='validate_url')
    ... def validate_url(url: str) -> bool:
    ...     if not url.startswith('http'):
    ...         raise ValueError("Invalid URL scheme")
    ...     return True
    >>>
    >>> # The error will be wrapped in ValidationError with context
    >>> validate_url('ftp://example.com')  # Raises ValidationError

See Also:
    - bunkrr.core.exceptions: Exception hierarchy
    - bunkrr.core.logger: Logging utilities
"""
import functools
import sys
import traceback
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union, cast

from .exceptions import BunkrrError, ERROR_CODES
from .logger import setup_logger

logger = setup_logger('bunkrr.error_handler')

# Type variables for generic function handling
F = TypeVar('F', bound=Callable[..., Any])
T = TypeVar('T')

class ErrorHandler:
    """Centralized error handler for the bunkrr package.
    
    This class provides static methods for handling errors consistently across
    the application. It includes functionality for error wrapping, logging,
    and context tracking.
    
    Example:
        >>> error = ValueError("Invalid input")
        >>> error_info = ErrorHandler.handle_error(error, "validation", reraise=False)
        >>> print(error_info['error_code'])
        'UNKNOWN_ERROR'
    """
    
    @staticmethod
    def handle_error(
        error: Union[BunkrrError, Exception],
        context: str,
        reraise: bool = True
    ) -> Dict[str, Any]:
        """Handle an error and optionally reraise it.
        
        Args:
            error: The error to handle. Can be a BunkrrError or any Exception.
            context: String describing where the error occurred.
            reraise: Whether to reraise the error after handling.
            
        Returns:
            Dict containing error information including:
                - type: Error class name
                - message: Error message
                - details: Additional error details
                - error_code: Standardized error code
                - context: Error context
                - traceback: Full error traceback
                
        Raises:
            The original error if reraise is True.
            
        Example:
            >>> try:
            ...     raise ValueError("Invalid value")
            ... except Exception as e:
            ...     error_info = ErrorHandler.handle_error(e, "validation", False)
            ...     print(error_info['type'])
            'ValueError'
        """
        error_info = ErrorHandler._create_error_info(error, context)
        
        # Log the error
        if isinstance(error, BunkrrError):
            logger.error(
                "%s: %s",
                error_info['error_code'],
                error_info['message'],
                extra=error_info
            )
        else:
            logger.error(
                "Unexpected error in %s: %s",
                context,
                str(error),
                exc_info=True
            )
        
        if reraise:
            raise error
            
        return error_info
        
    @staticmethod
    def wrap_errors(
        target_error: Type[BunkrrError],
        context: str,
        reraise: bool = True
    ) -> Callable[[F], F]:
        """Decorator to wrap function errors in a specific error type.
        
        Args:
            target_error: The BunkrrError subclass to wrap errors in.
            context: String describing the error context.
            reraise: Whether to reraise wrapped errors.
            
        Returns:
            A decorator function that wraps the target function.
            
        Example:
            >>> @ErrorHandler.wrap_errors(ValidationError, "url_check")
            ... def check_url(url: str) -> bool:
            ...     if not url.startswith('http'):
            ...         raise ValueError("Invalid URL")
            ...     return True
        """
        def decorator(func: F) -> F:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return func(*args, **kwargs)
                except target_error:
                    raise
                except Exception as e:
                    error = target_error(str(e), details=str(e.__class__.__name__))
                    ErrorHandler.handle_error(error, context, reraise)
                    return None  # Only reached if reraise is False
            return cast(F, wrapper)
        return decorator
        
    @staticmethod
    def async_wrap_errors(
        target_error: Type[BunkrrError],
        context: str,
        reraise: bool = True
    ) -> Callable[[F], F]:
        """Decorator to wrap async function errors in a specific error type."""
        def decorator(func: F) -> F:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await func(*args, **kwargs)
                except target_error:
                    raise
                except Exception as e:
                    error = target_error(str(e), details=str(e.__class__.__name__))
                    ErrorHandler.handle_error(error, context, reraise)
                    return None  # Only reached if reraise is False
            return cast(F, wrapper)
        return decorator
        
    @staticmethod
    def _create_error_info(
        error: Union[BunkrrError, Exception],
        context: str
    ) -> Dict[str, Any]:
        """Create a dictionary with error information."""
        if isinstance(error, BunkrrError):
            error_info = error.to_dict()
            error_info['error_code'] = ERROR_CODES.get(
                error.__class__,
                'UNKNOWN_ERROR'
            )
        else:
            error_info = {
                'type': error.__class__.__name__,
                'message': str(error),
                'details': None,
                'error_code': 'UNKNOWN_ERROR'
            }
            
        error_info.update({
            'context': context,
            'traceback': traceback.format_exc()
        })
        
        return error_info
        
def handle_errors(
    func: Optional[F] = None,
    *,
    target_error: Type[BunkrrError] = BunkrrError,
    context: Optional[str] = None,
    reraise: bool = True
) -> Union[Callable[[F], F], F]:
    """Decorator for handling errors in functions."""
    if func is None:
        return lambda f: handle_errors(
            f,
            target_error=target_error,
            context=context,
            reraise=reraise
        )
        
    actual_context = context or func.__name__
    
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except target_error:
            raise
        except Exception as e:
            error = target_error(str(e), details=str(e.__class__.__name__))
            ErrorHandler.handle_error(error, actual_context, reraise)
            return None  # Only reached if reraise is False
            
    return cast(F, wrapper)
    
def handle_async_errors(
    func: Optional[F] = None,
    *,
    target_error: Type[BunkrrError] = BunkrrError,
    context: Optional[str] = None,
    reraise: bool = True
) -> Union[Callable[[F], F], F]:
    """Decorator for handling errors in async functions."""
    if func is None:
        return lambda f: handle_async_errors(
            f,
            target_error=target_error,
            context=context,
            reraise=reraise
        )
        
    actual_context = context or func.__name__
    
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except target_error:
            raise
        except Exception as e:
            error = target_error(str(e), details=str(e.__class__.__name__))
            ErrorHandler.handle_error(error, actual_context, reraise)
            return None  # Only reached if reraise is False
            
    return cast(F, wrapper) 
