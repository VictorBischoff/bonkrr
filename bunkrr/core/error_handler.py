"""Error handling utilities for the bunkrr package."""
from typing import Optional, Dict, Any, Type, Callable, TypeVar, Union, List
from functools import wraps
import traceback
import inspect
import time
import json
import sys
import os
from collections import Counter, deque
from datetime import datetime, timedelta
from contextlib import contextmanager
from threading import local

from scrapy import signals
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.request import referer_str
from scrapy.exceptions import NotConfigured

from .logger import setup_logger
from .exceptions import BunkrrError

logger = setup_logger('bunkrr.error')

T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

class ErrorContext:
    """Context for error tracking and aggregation."""
    
    def __init__(self):
        """Initialize error context."""
        self.start_time = time.time()
        self.context_stack: List[Dict[str, Any]] = []
        self.error_info: Optional[Dict[str, Any]] = None
        self.spider = None  # Store spider reference for Scrapy integration
    
    def push(self, context: Dict[str, Any]) -> None:
        """Push context to stack."""
        if 'spider' in context:
            self.spider = context['spider']
        self.context_stack.append(context)
    
    def pop(self) -> Optional[Dict[str, Any]]:
        """Pop context from stack."""
        ctx = self.context_stack.pop() if self.context_stack else None
        if ctx and 'spider' in ctx and ctx['spider'] == self.spider:
            self.spider = None
        return ctx
    
    def get_full_context(self) -> Dict[str, Any]:
        """Get merged context from stack."""
        full_context = {}
        for ctx in self.context_stack:
            full_context.update(ctx)
        if self.spider:
            full_context['spider'] = self.spider.name
            full_context['spider_stats'] = dict(self.spider.crawler.stats.get_stats())
        return full_context
    
    def set_error(self, error_info: Dict[str, Any]) -> None:
        """Set error information."""
        self.error_info = error_info
        if self.spider:
            # Update spider stats
            stats = self.spider.crawler.stats
            stats.inc_value('error_count')
            stats.inc_value(f'error_count/{error_info["type"]}')
            if 'url' in error_info:
                stats.inc_value(f'error_count/by_url/{error_info["url"]}')

class ErrorStats:
    """Track error statistics with improved aggregation."""
    
    def __init__(self, window_size: int = 3600):  # 1 hour window
        self.window_size = window_size
        self.error_counts = Counter()
        self.error_times: deque[tuple[str, float]] = deque()
        self.last_cleanup = time.time()
        
        # Enhanced tracking
        self.error_durations: Dict[str, List[float]] = {}
        self.error_contexts: Dict[str, Counter] = {}
        self.error_patterns: Dict[str, Counter] = {}
        self.spider_errors: Dict[str, Counter] = {}  # Track errors by spider
    
    def add_error(
        self,
        error_type: str,
        duration: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add error occurrence with enhanced tracking."""
        now = time.time()
        
        # Basic tracking
        self.error_counts[error_type] += 1
        self.error_times.append((error_type, now))
        
        # Track spider-specific errors
        if context and 'spider' in context:
            spider_name = context['spider']
            if spider_name not in self.spider_errors:
                self.spider_errors[spider_name] = Counter()
            self.spider_errors[spider_name][error_type] += 1
        
        # Track durations
        if duration is not None:
            if error_type not in self.error_durations:
                self.error_durations[error_type] = []
            self.error_durations[error_type].append(duration)
        
        # Track contexts
        if context:
            if error_type not in self.error_contexts:
                self.error_contexts[error_type] = Counter()
            context_key = json.dumps(
                sorted(context.items()),
                sort_keys=True
            )
            self.error_contexts[error_type][context_key] += 1
        
        # Log to Scrapy stats if available
        if context and 'spider' in context and hasattr(context['spider'], 'crawler'):
            stats = context['spider'].crawler.stats
            stats.inc_value(f'error_count/{error_type}')
            if 'url' in context:
                stats.inc_value(f'error_count/by_url/{context["url"]}')
                referer = referer_str(context.get('request'))
                if referer:
                    stats.inc_value(f'error_count/by_referer/{referer}')
        
        # Cleanup old errors periodically
        if now - self.last_cleanup > 60:  # Cleanup every minute
            self._cleanup(now)
    
    def _cleanup(self, now: float) -> None:
        """Remove errors outside the window."""
        cutoff = now - self.window_size
        
        # Clean error times
        while self.error_times and self.error_times[0][1] < cutoff:
            error_type, _ = self.error_times.popleft()
            self.error_counts[error_type] -= 1
            if self.error_counts[error_type] <= 0:
                del self.error_counts[error_type]
        
        # Clean durations
        for error_type in list(self.error_durations.keys()):
            if not self.error_counts[error_type]:
                del self.error_durations[error_type]
        
        # Clean contexts
        for error_type in list(self.error_contexts.keys()):
            if not self.error_counts[error_type]:
                del self.error_contexts[error_type]
        
        self.last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive error statistics."""
        now = time.time()
        self._cleanup(now)
        
        stats = {
            'window_size': self.window_size,
            'total_errors': sum(self.error_counts.values()),
            'unique_errors': len(self.error_counts),
            'error_counts': dict(self.error_counts),
            'errors_per_minute': (
                sum(self.error_counts.values()) * 60 / self.window_size
            ),
            'error_patterns': {}
        }
        
        # Add duration statistics
        stats['durations'] = {}
        for error_type, durations in self.error_durations.items():
            if durations:
                stats['durations'][error_type] = {
                    'min': min(durations),
                    'max': max(durations),
                    'avg': sum(durations) / len(durations)
                }
        
        # Add context patterns
        stats['contexts'] = {}
        for error_type, contexts in self.error_contexts.items():
            if contexts:
                stats['contexts'][error_type] = {
                    k: v for k, v in contexts.most_common(5)
                }
        
        return stats

class ErrorHandler:
    """Centralized error handling with enhanced context."""
    
    _handlers: Dict[Type[Exception], Callable] = {}
    _stats = ErrorStats()
    _context = local()
    
    @classmethod
    def get_context(cls) -> ErrorContext:
        """Get or create thread-local error context."""
        if not hasattr(cls._context, 'context'):
            cls._context.context = ErrorContext()
        return cls._context.context
    
    @classmethod
    @contextmanager
    def error_context(cls, **kwargs: Any):
        """Context manager for error handling context."""
        context = cls.get_context()
        context.push(kwargs)
        try:
            yield context
        finally:
            context.pop()
    
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
    def handle(
        cls,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Handle error with enhanced context and tracking."""
        error_type = type(error).__name__
        start_time = cls.get_context().start_time
        duration = time.time() - start_time
        
        # Merge contexts
        full_context = cls.get_context().get_full_context()
        if context:
            full_context.update(context)
        
        # Create rich error info
        error_info = {
            'type': error_type,
            'message': str(error),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat(),
            'duration': duration,
            'context': full_context,
            'environment': {
                'python_version': sys.version,
                'platform': sys.platform,
                'cwd': os.getcwd()
            }
        }
        
        # Add call stack info
        if hasattr(error, '__traceback__'):
            stack = []
            for frame in traceback.extract_tb(error.__traceback__):
                stack.append({
                    'file': frame.filename,
                    'line': frame.lineno,
                    'function': frame.name,
                    'code': frame.line,
                    'locals': cls._get_frame_locals(frame)
                })
            error_info['stack'] = stack
        
        # Add error attributes
        if isinstance(error, BunkrrError):
            error_info.update(error.to_dict())
        
        # Track error
        cls._stats.add_error(
            error_type,
            duration=duration,
            context=full_context
        )
        
        # Store in context
        cls.get_context().set_error(error_info)
        
        # Handle error
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
        if cls._stats.get_stats()['total_errors'] % 10 == 0:
            cls._log_stats()
    
    @classmethod
    def wrap(
        cls,
        target_error: Type[Exception] = Exception,
        context: Optional[Union[str, Dict[str, Any]]] = None,
        reraise: bool = True
    ) -> Callable[[F], F]:
        """Decorator for error handling with context."""
        # Convert string context to dict
        if isinstance(context, str):
            context = {'context': context}
        elif context is None:
            context = {}
            
        def decorator(func: F) -> F:
            if inspect.iscoroutinefunction(func):
                @wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    with cls.error_context(
                        function=func.__name__,
                        args=args,
                        kwargs=kwargs,
                        **context
                    ):
                        try:
                            return await func(*args, **kwargs)
                        except Exception as e:
                            if isinstance(e, target_error):
                                cls.handle(e)
                                if reraise:
                                    raise
                            else:
                                raise
                return async_wrapper
            else:
                @wraps(func)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    with cls.error_context(
                        function=func.__name__,
                        args=args,
                        kwargs=kwargs,
                        **context
                    ):
                        try:
                            return func(*args, **kwargs)
                        except Exception as e:
                            if isinstance(e, target_error):
                                cls.handle(e)
                                if reraise:
                                    raise
                            else:
                                raise
                return sync_wrapper
            
            if inspect.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
            
        return decorator
    
    @classmethod
    def wrap_async(
        cls,
        target_error: Type[Exception] = Exception,
        context: Optional[Union[str, Dict[str, Any]]] = None,
        reraise: bool = True
    ) -> Callable[[F], F]:
        """Decorator specifically for async error handling with context."""
        # Convert string context to dict
        if isinstance(context, str):
            context = {'context': context}
        elif context is None:
            context = {}
            
        def decorator(func: F) -> F:
            if not inspect.iscoroutinefunction(func):
                raise TypeError(f"Function {func.__name__} must be async")
            
            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                # Build context
                ctx = context.copy()
                
                # Check if this is an instance method
                try:
                    if args and hasattr(args[0], '__class__') and hasattr(args[0].__class__, func.__name__):
                        # Instance method - first arg is self/cls
                        instance = args[0]
                        ctx['function'] = f"{instance.__class__.__name__}.{func.__name__}"
                        ctx['instance'] = instance.__class__.__name__
                    else:
                        # Standalone function
                        ctx['function'] = func.__name__
                except Exception:
                    # Fallback to function name if instance check fails
                    ctx['function'] = func.__name__
                
                with cls.error_context(**ctx):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        if isinstance(e, target_error):
                            cls.handle(e)
                            if reraise:
                                raise
                        else:
                            raise
            return wrapper
        return decorator
    
    @classmethod
    def wrap_sync(
        cls,
        target_error: Type[Exception] = Exception,
        context: Optional[Dict[str, Any]] = None,
        reraise: bool = True
    ) -> Callable[[F], F]:
        """Decorator specifically for sync error handling with context."""
        def decorator(func: F) -> F:
            if inspect.iscoroutinefunction(func):
                raise TypeError(f"Function {func.__name__} must be synchronous")
            
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with cls.error_context(
                    function=func.__name__,
                    args=args,
                    kwargs=kwargs,
                    is_async=False,
                    **(context or {})
                ):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if isinstance(e, target_error):
                            cls.handle(e)
                            if reraise:
                                raise
                        else:
                            raise
            return wrapper
        return decorator
    
    @classmethod
    def _default_handler(cls, error: Exception, error_info: Dict[str, Any]) -> None:
        """Enhanced default error handling logic."""
        # Get spider context if available
        context = error_info.get('context', {})
        spider = context.get('spider')
        
        # Create detailed error message
        error_msg = (
            f"{'Spider ' + spider.name + ' - ' if spider else ''}"
            f"[{error_info['type']}] {error_info['message']}\n"
            f"Duration: {error_info.get('duration', 0):.2f}s"
        )
        
        # Add request info if available
        if 'request' in context:
            req = context['request']
            error_msg += f"\nURL: {req.url}"
            if req.callback:
                error_msg += f"\nCallback: {req.callback.__name__}"
            if req.errback:
                error_msg += f"\nErrback: {req.errback.__name__}"
            
        # Add spider stats if available
        if spider and hasattr(spider, 'crawler'):
            stats = spider.crawler.stats.get_stats()
            error_msg += "\nSpider Stats:\n" + json.dumps(
                {k: v for k, v in stats.items() if 'error' in k.lower()},
                indent=2
            )
        
        # Add context and stack trace
        error_msg += (
            f"\nContext: {json.dumps(context, indent=2)}\n"
            f"Stack: {cls._format_stack(error_info.get('stack', []))}"
        )
        
        # Log appropriately based on error type
        if isinstance(error, BunkrrError):
            logger.error(error_msg, extra=error_info)
            if spider:
                spider.crawler.stats.inc_value(
                    f'error_count/handled/{error_info["type"]}'
                )
        else:
            logger.exception(error_msg, exc_info=failure_to_exc_info(error), extra=error_info)
            if spider:
                spider.crawler.stats.inc_value(
                    f'error_count/unhandled/{error_info["type"]}'
                )
        
        # Signal error if spider is available
        if spider:
            spider.crawler.signals.send_catch_log(
                signal=signals.spider_error,
                failure=error,
                response=context.get('response'),
                spider=spider
            )
    
    @staticmethod
    def _get_frame_locals(frame: traceback.FrameSummary) -> Dict[str, str]:
        """Get relevant local variables from frame."""
        try:
            if hasattr(frame, 'f_locals'):
                locals_dict = {}
                for k, v in frame.f_locals.items():
                    if k.startswith('_'):
                        continue
                    try:
                        # Handle Scrapy objects specially
                        if k == 'self' and hasattr(v, 'crawler'):
                            locals_dict[k] = f"<Spider {v.name}>"
                        elif k == 'response' and hasattr(v, 'url'):
                            locals_dict[k] = f"<Response {v.status} {v.url}>"
                        elif k == 'request' and hasattr(v, 'url'):
                            locals_dict[k] = f"<Request {v.method} {v.url}>"
                        else:
                            locals_dict[k] = repr(v)
                    except Exception:
                        locals_dict[k] = '<unprintable>'
                return locals_dict
        except Exception:
            pass
        return {}
    
    @staticmethod
    def _format_stack(stack: List[Dict[str, Any]]) -> str:
        """Format stack trace for logging."""
        if not stack:
            return "No stack trace available"
        
        formatted = []
        for frame in stack:
            frame_str = (
                f"File \"{frame['file']}\", "
                f"line {frame['line']}, "
                f"in {frame['function']}\n"
            )
            if frame.get('code'):
                frame_str += f"  {frame['code']}\n"
            if frame.get('locals'):
                frame_str += "  Locals:\n"
                for name, value in frame['locals'].items():
                    frame_str += f"    {name} = {value}\n"
            formatted.append(frame_str)
        
        return "\n".join(formatted)
    
    @classmethod
    def _log_stats(cls) -> None:
        """Log comprehensive error statistics."""
        stats = cls._stats.get_stats()
        
        # Add spider-specific error stats
        stats['spider_errors'] = {
            spider: dict(counts)
            for spider, counts in cls._stats.spider_errors.items()
        }
        
        # Calculate error rates
        total_errors = stats['total_errors']
        if total_errors > 0:
            stats['error_rates'] = {
                'by_type': {
                    error_type: count / total_errors
                    for error_type, count in stats['error_counts'].items()
                }
            }
            if stats['spider_errors']:
                stats['error_rates']['by_spider'] = {
                    spider: sum(counts.values()) / total_errors
                    for spider, counts in stats['spider_errors'].items()
                }
        
        logger.info(
            "Error Statistics:\n%s",
            json.dumps(stats, indent=2)
        )

# Standalone function aliases for backward compatibility
def handle_errors(
    target_error: Type[Exception] = Exception,
    context: Optional[Dict[str, Any]] = None,
    reraise: bool = True
) -> Callable[[F], F]:
    """Alias for ErrorHandler.wrap for backward compatibility."""
    return ErrorHandler.wrap(target_error, context, reraise)

def handle_async_errors(
    target_error: Type[Exception] = Exception,
    context: Optional[Dict[str, Any]] = None,
    reraise: bool = True
) -> Callable[[F], F]:
    """Alias for ErrorHandler.wrap_async for backward compatibility."""
    return ErrorHandler.wrap_async(target_error, context, reraise)

def handle_sync_errors(
    target_error: Type[Exception] = Exception,
    context: Optional[Dict[str, Any]] = None,
    reraise: bool = True
) -> Callable[[F], F]:
    """Alias for ErrorHandler.wrap_sync for backward compatibility."""
    return ErrorHandler.wrap_sync(target_error, context, reraise)

# Additional aliases
wrap = handle_errors
wrap_sync = handle_sync_errors
wrap_async = handle_async_errors
