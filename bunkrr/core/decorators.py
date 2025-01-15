"""Error handling decorators for the bunkrr package."""
from typing import Optional, Dict, Any, Type, Callable, TypeVar, Union

from .error_handler import ErrorHandler
from .exceptions import BunkrrError

F = TypeVar('F', bound=Callable[..., Any])

def handle_errors(
    target_error: Type[Exception] = BunkrrError,
    context: Optional[Union[str, Dict[str, Any]]] = None,
    reraise: bool = True
) -> Callable[[F], F]:
    """Convenience decorator for handling errors in sync functions.
    
    Args:
        target_error: Type of error to handle
        context: Optional context string or dict
        reraise: Whether to reraise the error after handling
        
    Returns:
        Decorated function
    """
    return ErrorHandler.wrap(target_error, context, reraise)

def handle_async_errors(
    target_error: Type[Exception] = BunkrrError,
    context: Optional[Union[str, Dict[str, Any]]] = None,
    reraise: bool = True
) -> Callable[[F], F]:
    """Convenience decorator for handling errors in async functions.
    
    Args:
        target_error: Type of error to handle
        context: Optional context string or dict
        reraise: Whether to reraise the error after handling
        
    Returns:
        Decorated function
    """
    return ErrorHandler.wrap_async(target_error, context, reraise) 
