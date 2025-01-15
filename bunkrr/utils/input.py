"""Input utilities for the bunkrr package."""
import os
from pathlib import Path
from typing import List, Optional, Set, Tuple

from ..core.exceptions import ValidationError
from ..core.logger import setup_logger
from .filesystem import is_valid_path
from .validation import url_validator

logger = setup_logger('bunkrr.input')

def parse_urls(input_text: str) -> List[str]:
    """Parse URLs from input text."""
    # Split by common separators
    urls = set()
    for line in input_text.splitlines():
        line = line.strip()
        if not line:
            continue
            
        # Split by common separators
        parts = line.replace(',', ' ').replace(';', ' ').split()
        urls.update(parts)
    
    # Validate each URL
    valid_urls = []
    for url in urls:
        try:
            url_validator.validate_url(url)
            valid_urls.append(url)
        except ValidationError as e:
            logger.warning("Skipping invalid URL %s: %s", url, str(e))
    
    return valid_urls

def parse_path(
    path: str,
    create: bool = False,
    must_exist: bool = False
) -> Path:
    """Parse and validate path."""
    try:
        # Expand user and environment variables
        expanded = os.path.expanduser(os.path.expandvars(path))
        path_obj = Path(expanded).resolve()
        
        # Check if path exists
        if must_exist and not path_obj.exists():
            raise ValidationError(
                f"Path does not exist: {path_obj}",
                "Please provide an existing path"
            )
        
        # Create directory if needed
        if create and not path_obj.exists():
            try:
                path_obj.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ValidationError(
                    f"Failed to create directory: {path_obj}",
                    str(e)
                )
        
        # Validate path
        if not is_valid_path(path_obj):
            raise ValidationError(
                f"Invalid path: {path_obj}",
                "Path must be writable"
            )
        
        return path_obj
        
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(f"Invalid path: {path}", str(e))

def parse_bool(value: str) -> bool:
    """Parse boolean value from string."""
    value = value.lower().strip()
    
    if value in {'1', 'true', 'yes', 'y', 'on'}:
        return True
        
    if value in {'0', 'false', 'no', 'n', 'off'}:
        return False
        
    raise ValidationError(
        f"Invalid boolean value: {value}",
        "Please use yes/no, true/false, 1/0"
    )

def parse_int(
    value: str,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None
) -> int:
    """Parse integer value from string with range validation."""
    try:
        result = int(value)
        
        if min_val is not None and result < min_val:
            raise ValidationError(
                f"Value {result} is below minimum {min_val}",
                f"Please enter a value >= {min_val}"
            )
            
        if max_val is not None and result > max_val:
            raise ValidationError(
                f"Value {result} is above maximum {max_val}",
                f"Please enter a value <= {max_val}"
            )
            
        return result
        
    except ValueError:
        raise ValidationError(
            f"Invalid integer value: {value}",
            "Please enter a valid number"
        )

def parse_float(
    value: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None
) -> float:
    """Parse float value from string with range validation."""
    try:
        result = float(value)
        
        if min_val is not None and result < min_val:
            raise ValidationError(
                f"Value {result} is below minimum {min_val}",
                f"Please enter a value >= {min_val}"
            )
            
        if max_val is not None and result > max_val:
            raise ValidationError(
                f"Value {result} is above maximum {max_val}",
                f"Please enter a value <= {max_val}"
            )
            
        return result
        
    except ValueError:
        raise ValidationError(
            f"Invalid float value: {value}",
            "Please enter a valid number"
        )

def parse_choice(
    value: str,
    choices: Set[str],
    case_sensitive: bool = False
) -> str:
    """Parse choice from set of valid options."""
    if not case_sensitive:
        value = value.lower()
        choices = {c.lower() for c in choices}
    
    if value not in choices:
        raise ValidationError(
            f"Invalid choice: {value}",
            f"Please choose from: {', '.join(sorted(choices))}"
        )
    
    return value

def parse_key_value(text: str) -> Tuple[str, str]:
    """Parse key-value pair from string."""
    try:
        key, value = map(str.strip, text.split('=', 1))
        
        if not key:
            raise ValidationError(
                "Empty key in key-value pair",
                "Format should be key=value"
            )
            
        return key, value
        
    except ValueError:
        raise ValidationError(
            f"Invalid key-value format: {text}",
            "Format should be key=value"
        ) 
