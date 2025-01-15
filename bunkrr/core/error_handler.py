"""Error handling utilities for the bunkrr package."""
from typing import Optional, Dict, Any, Type, Callable, TypeVar, Union
from functools import wraps
import traceback
import inspect

from .logger import setup_logger
from .exceptions import BunkrrError

logger = setup_logger('bunkrr.error')

T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

class ErrorContext:
    """Context manager for error handling."""
    
    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            ErrorHandler.handle(exc_val, self.context)
        return False

class ErrorHandler:
    """Centralized error handling for the bunkrr package."""
    
    _handlers: Dict[Type[Exception], Callable] = {}
    
    @classmethod
    def register(cls, error_type: Type[Exception]) -> Callable[[F], F]:
        """Decorator to register error handler for specific error type."""
        def decorator(handler: F) -> F:
            cls._handlers[error_type] = handler
            return handler
        return decorator
    
    @classmethod
    def handle(cls, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """Handle error with registered handler or default handling."""
        error_info = {
            'type': type(error).__name__,
            'message': str(error),
            'traceback': traceback.format_exc(),
            **(context or {})
        }
        
        handler = cls._handlers.get(type(error))
        if handler:
            handler(error, error_info)
        else:
            cls._default_handler(error, error_info)
    
    @classmethod
    def _default_handler(cls, error: Exception, error_info: Dict[str, Any]) -> None:
        """Default error handling logic."""
        if isinstance(error, BunkrrError):
            logger.error(
                "Application error: %s",
                error_info['message'],
                extra=error_info
            )
        else:
            logger.exception(
                "Unexpected error: %s",
                error_info['message'],
                extra=error_info
            )
    
    @classmethod
    def wrap(cls, func: Optional[F] = None, *, context: Optional[Dict[str, Any]] = None) -> Union[F, Callable[[F], F]]:
        """Decorator for error handling that works with both sync and async functions."""
        def decorator(f: F) -> F:
            is_async = inspect.iscoroutinefunction(f)
            
            if is_async:
                @wraps(f)
                async def async_wrapper(*args, **kwargs):
                    try:
                        return await f(*args, **kwargs)
                    except Exception as e:
                        cls.handle(e, {
                            'function': f.__name__,
                            'args': args,
                            'kwargs': kwargs,
                            **(context or {})
                        })
                        raise
                return async_wrapper
            else:
                @wraps(f)
                def sync_wrapper(*args, **kwargs):
                    try:
                        return f(*args, **kwargs)
                    except Exception as e:
                        cls.handle(e, {
                            'function': f.__name__,
                            'args': args,
                            'kwargs': kwargs,
                            **(context or {})
                        })
                        raise
                return sync_wrapper
        
        return decorator if func is None else decorator(func)
    
    # Aliases for backward compatibility
    wrap_sync = wrap
    wrap_async = wrap 
