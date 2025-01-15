"""Error handling utilities for the bunkrr package."""
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
    """Centralized error handler for the bunkrr package."""
    
    @staticmethod
    def handle_error(
        error: Union[BunkrrError, Exception],
        context: str,
        reraise: bool = True
    ) -> Dict[str, Any]:
        """Handle an error and optionally reraise it."""
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
        """Decorator to wrap function errors in a specific error type."""
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
