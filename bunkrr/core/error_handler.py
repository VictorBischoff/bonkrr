"""Error handling utilities for the bunkrr package."""
from typing import Optional, Dict, Any, Type, Callable, TypeVar, Union, Counter
from functools import wraps
import traceback
import inspect
import time
import json
from collections import Counter, deque
from datetime import datetime, timedelta

from .logger import setup_logger
from .exceptions import BunkrrError

logger = setup_logger('bunkrr.error')

T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

class ErrorStats:
    """Track error statistics."""
    
    def __init__(self, window_size: int = 3600):  # 1 hour window
        self.window_size = window_size
        self.error_counts = Counter()
        self.error_times: deque[tuple[str, float]] = deque()
        self.last_cleanup = time.time()
    
    def add_error(self, error_type: str) -> None:
        """Add error occurrence to statistics."""
        now = time.time()
        self.error_counts[error_type] += 1
        self.error_times.append((error_type, now))
        
        # Cleanup old errors periodically
        if now - self.last_cleanup > 60:  # Cleanup every minute
            self._cleanup(now)
    
    def _cleanup(self, now: float) -> None:
        """Remove errors outside the window."""
        cutoff = now - self.window_size
        while self.error_times and self.error_times[0][1] < cutoff:
            error_type, _ = self.error_times.popleft()
            self.error_counts[error_type] -= 1
            if self.error_counts[error_type] <= 0:
                del self.error_counts[error_type]
        self.last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current error statistics."""
        now = time.time()
        self._cleanup(now)
        
        return {
            'window_size': self.window_size,
            'total_errors': sum(self.error_counts.values()),
            'unique_errors': len(self.error_counts),
            'error_counts': dict(self.error_counts),
            'errors_per_minute': sum(self.error_counts.values()) * 60 / self.window_size
        }

class ErrorContext:
    """Context manager for error handling."""
    
    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}
        self.start_time = time.time()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self.context['duration'] = time.time() - self.start_time
            ErrorHandler.handle(exc_val, self.context)
        return False

class ErrorHandler:
    """Centralized error handling for the bunkrr package."""
    
    _handlers: Dict[Type[Exception], Callable] = {}
    _stats = ErrorStats()
    
    @classmethod
    def register(cls, error_type: Type[Exception]) -> Callable[[F], F]:
        """Decorator to register error handler for specific error type."""
        def decorator(handler: F) -> F:
            cls._handlers[error_type] = handler
            logger.info(
                "Registered error handler for %s: %s",
                error_type.__name__,
                handler.__name__
            )
            return handler
        return decorator
    
    @classmethod
    def handle(cls, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """Handle error with registered handler or default handling."""
        error_type = type(error).__name__
        cls._stats.add_error(error_type)
        
        error_info = {
            'type': error_type,
            'message': str(error),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat(),
            'stats': cls._stats.get_stats(),
            **(context or {})
        }
        
        # Add call stack info if available
        if hasattr(error, '__traceback__'):
            stack = []
            for frame in traceback.extract_tb(error.__traceback__):
                stack.append({
                    'file': frame.filename,
                    'line': frame.lineno,
                    'function': frame.name,
                    'code': frame.line
                })
            error_info['stack'] = stack
        
        handler = cls._handlers.get(type(error))
        if handler:
            logger.debug(
                "Using registered handler %s for error type %s",
                handler.__name__,
                error_type
            )
            handler(error, error_info)
        else:
            cls._default_handler(error, error_info)
        
        # Log error statistics periodically
        if cls._stats.get_stats()['total_errors'] % 10 == 0:  # Every 10 errors
            cls._log_stats()
    
    @classmethod
    def _default_handler(cls, error: Exception, error_info: Dict[str, Any]) -> None:
        """Default error handling logic."""
        if isinstance(error, BunkrrError):
            logger.error(
                "Application error [%s] - %s\nContext: %s",
                error_info['type'],
                error_info['message'],
                json.dumps(error_info, indent=2),
                extra=error_info
            )
        else:
            logger.exception(
                "Unexpected error [%s] - %s\nContext: %s",
                error_info['type'],
                error_info['message'],
                json.dumps(error_info, indent=2),
                extra=error_info
            )
    
    @classmethod
    def _log_stats(cls) -> None:
        """Log error statistics."""
        stats = cls._stats.get_stats()
        logger.info(
            "Error statistics - %s",
            json.dumps(stats, indent=2)
        )
    
    @classmethod
    def wrap(cls, func: Optional[F] = None, *, context: Optional[Dict[str, Any]] = None) -> Union[F, Callable[[F], F]]:
        """Decorator for error handling that works with both sync and async functions."""
        def decorator(f: F) -> F:
            is_async = inspect.iscoroutinefunction(f)
            
            if is_async:
                @wraps(f)
                async def async_wrapper(*args, **kwargs):
                    start_time = time.time()
                    try:
                        return await f(*args, **kwargs)
                    except Exception as e:
                        cls.handle(e, {
                            'function': f.__name__,
                            'args': args,
                            'kwargs': kwargs,
                            'duration': time.time() - start_time,
                            **(context or {})
                        })
                        raise
                return async_wrapper
            else:
                @wraps(f)
                def sync_wrapper(*args, **kwargs):
                    start_time = time.time()
                    try:
                        return f(*args, **kwargs)
                    except Exception as e:
                        cls.handle(e, {
                            'function': f.__name__,
                            'args': args,
                            'kwargs': kwargs,
                            'duration': time.time() - start_time,
                            **(context or {})
                        })
                        raise
                return sync_wrapper
        
        return decorator if func is None else decorator(func)
    
    # Aliases for backward compatibility
    wrap_sync = wrap
    wrap_async = wrap 
