"""Core utilities for the bunkrr package."""
import asyncio
import functools
import os
import signal
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any, AsyncGenerator, Callable, Optional,
    Set, TypeVar, Union
)

from ..core.exceptions import ValidationError
from ..core.logger import setup_logger
from .storage import is_valid_path

logger = setup_logger('bunkrr.core')

T = TypeVar('T')

class CancellationToken:
    """Token for managing cancellation of async operations."""
    
    def __init__(self):
        """Initialize cancellation token."""
        self._cancelled = False
        self._callbacks: Set[Callable[[], None]] = set()
    
    def cancel(self) -> None:
        """Cancel the operation."""
        if not self._cancelled:
            self._cancelled = True
            for callback in self._callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error("Cancellation callback error: %s", str(e))
    
    @property
    def is_cancelled(self) -> bool:
        """Check if operation is cancelled."""
        return self._cancelled
    
    def add_callback(self, callback: Callable[[], None]) -> None:
        """Add cancellation callback."""
        if not self._cancelled:
            self._callbacks.add(callback)
    
    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove cancellation callback."""
        self._callbacks.discard(callback)

@dataclass
class PathValidator:
    """Path validation with configurable options."""
    
    create_missing: bool = False
    require_exists: bool = False
    require_writable: bool = True
    
    def validate(self, path: Union[str, Path]) -> Path:
        """Validate path and return resolved Path object."""
        try:
            # Expand user and environment variables
            if isinstance(path, str):
                expanded = os.path.expanduser(os.path.expandvars(path))
                path_obj = Path(expanded).resolve()
            else:
                path_obj = path.resolve()
            
            # Check existence
            if self.require_exists and not path_obj.exists():
                raise ValidationError(
                    message="Path does not exist",
                    field="path",
                    value=str(path_obj)
                )
            
            # Create if needed
            if self.create_missing and not path_obj.exists():
                try:
                    path_obj.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    raise ValidationError(
                        message="Failed to create directory",
                        field="path",
                        value=str(path_obj),
                        details=str(e)
                    )
            
            # Check writability
            if self.require_writable and not is_valid_path(path_obj):
                raise ValidationError(
                    message="Path not writable",
                    field="path",
                    value=str(path_obj)
                )
            
            return path_obj
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise ValidationError(
                message="Invalid path",
                field="path",
                value=str(path),
                details=str(e)
            )

@dataclass
class ConfigValidator:
    """Configuration value validation."""
    
    name: str
    value_type: Any
    min_val: Optional[Any] = None
    max_val: Optional[Any] = None
    required: bool = True
    
    def validate(self, value: Any) -> None:
        """Validate configuration value."""
        if value is None:
            if self.required:
                raise ValidationError(
                    message=f"{self.name} is required",
                    field=self.name,
                    value=value
                )
            return
        
        if not isinstance(value, self.value_type):
            raise ValidationError(
                message=f"{self.name} must be of type {self.value_type.__name__}",
                field=self.name,
                value=value,
                details=f"Got type {type(value).__name__}"
            )
        
        if self.min_val is not None and value < self.min_val:
            raise ValidationError(
                message=f"{self.name} must be at least {self.min_val}",
                field=self.name,
                value=value,
                details=f"Minimum value: {self.min_val}"
            )
        
        if self.max_val is not None and value > self.max_val:
            raise ValidationError(
                message=f"{self.name} must be at most {self.max_val}",
                field=self.name,
                value=value,
                details=f"Maximum value: {self.max_val}"
            )

# Create global validator instances
path_validator = PathValidator()

# Convenience functions
def validate_path(
    path: Union[str, Path],
    create: bool = False,
    must_exist: bool = False,
    require_writable: bool = True
) -> Path:
    """Validate path with options."""
    validator = PathValidator(
        create_missing=create,
        require_exists=must_exist,
        require_writable=require_writable
    )
    return validator.validate(path)

def validate_config(
    name: str,
    value: Any,
    value_type: Any,
    min_val: Optional[Any] = None,
    max_val: Optional[Any] = None,
    required: bool = True
) -> None:
    """Validate configuration value."""
    validator = ConfigValidator(
        name=name,
        value_type=value_type,
        min_val=min_val,
        max_val=max_val,
        required=required
    )
    validator.validate(value)

@asynccontextmanager
async def run_in_executor(
    func: Callable[..., T],
    *args: Any,
    **kwargs: Any
) -> AsyncGenerator[T, None]:
    """Run function in thread pool executor."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        try:
            result = await loop.run_in_executor(
                pool,
                functools.partial(func, *args, **kwargs)
            )
            yield result
        finally:
            pool.shutdown(wait=True)

def handle_signals(handler: Callable[[int, Optional[Any]], None]) -> None:
    """Set up signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler) 
