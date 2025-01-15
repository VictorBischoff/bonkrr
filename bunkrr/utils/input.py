"""Input utilities for the bunkrr package."""
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union, TypeVar, Generic

import yaml
from jsonschema import validate, ValidationError as JsonSchemaError

from ..core.exceptions import ValidationError, ConfigError
from ..core.logger import setup_logger
from .core import validate_path, validate_config
from .storage import sanitize_filename

logger = setup_logger('bunkrr.input')

T = TypeVar('T')

@dataclass
class InputConfig:
    """Configuration for input validation."""
    
    required: bool = True
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    choices: Optional[Set[str]] = None
    strip: bool = True
    lower: bool = False
    
    def validate(self, value: str) -> str:
        """Validate and normalize input string."""
        if not value and self.required:
            raise ValidationError(
                message="Input cannot be empty",
                field="input",
                value=value
            )
        
        # Normalize
        if self.strip:
            value = value.strip()
        if self.lower:
            value = value.lower()
        
        # Length checks
        if self.min_length is not None and len(value) < self.min_length:
            raise ValidationError(
                message=f"Input must be at least {self.min_length} characters",
                field="input",
                value=value
            )
        
        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError(
                message=f"Input cannot exceed {self.max_length} characters",
                field="input",
                value=value
            )
        
        # Pattern check
        if self.pattern and not re.match(self.pattern, value):
            raise ValidationError(
                message="Input format is invalid",
                field="input",
                value=value,
                details=f"Must match pattern: {self.pattern}"
            )
        
        # Choices check
        if self.choices and value not in self.choices:
            raise ValidationError(
                message="Invalid choice",
                field="input",
                value=value,
                details=f"Must be one of: {', '.join(sorted(self.choices))}"
            )
        
        return value

@dataclass
class ConfigSchema(Generic[T]):
    """Configuration schema with validation."""
    
    schema: Dict[str, Any]
    defaults: Dict[str, Any] = field(default_factory=dict)
    required_fields: Set[str] = field(default_factory=set)
    
    def validate(self, config: Dict[str, Any]) -> T:
        """Validate configuration against schema."""
        try:
            # Add defaults for missing fields
            for key, value in self.defaults.items():
                if key not in config:
                    config[key] = value
            
            # Check required fields
            missing = self.required_fields - set(config.keys())
            if missing:
                raise ConfigError(
                    message="Missing required fields",
                    details=f"Required fields: {', '.join(sorted(missing))}"
                )
            
            # Validate against JSON schema
            validate(instance=config, schema=self.schema)
            return config  # type: ignore
            
        except JsonSchemaError as e:
            raise ConfigError(
                message="Invalid configuration",
                details=str(e)
            )
        except Exception as e:
            if isinstance(e, ConfigError):
                raise
            raise ConfigError(
                message="Configuration validation failed",
                details=str(e)
            )

class ConfigLoader:
    """Load and validate configuration from various sources."""
    
    def __init__(self, schema: ConfigSchema[T]):
        """Initialize config loader with schema."""
        self.schema = schema
    
    def load_file(self, path: Union[str, Path]) -> T:
        """Load configuration from file."""
        path_obj = validate_path(path, must_exist=True)
        
        try:
            with path_obj.open('r') as f:
                if path_obj.suffix == '.json':
                    config = json.load(f)
                elif path_obj.suffix in {'.yml', '.yaml'}:
                    config = yaml.safe_load(f)
                else:
                    raise ConfigError(
                        message="Unsupported file format",
                        details=f"Supported formats: .json, .yml, .yaml"
                    )
            
            return self.schema.validate(config)
            
        except Exception as e:
            if isinstance(e, (ConfigError, ValidationError)):
                raise
            raise ConfigError(
                message=f"Failed to load configuration from {path_obj}",
                details=str(e)
            )
    
    def load_env(self, prefix: str = 'BUNKRR_') -> T:
        """Load configuration from environment variables."""
        config: Dict[str, Any] = {}
        
        try:
            for key, value in os.environ.items():
                if key.startswith(prefix):
                    config_key = key[len(prefix):].lower()
                    
                    # Try to parse as JSON for complex values
                    try:
                        config[config_key] = json.loads(value)
                    except json.JSONDecodeError:
                        config[config_key] = value
            
            return self.schema.validate(config)
            
        except Exception as e:
            if isinstance(e, ConfigError):
                raise
            raise ConfigError(
                message="Failed to load configuration from environment",
                details=str(e)
            )
    
    def merge_configs(self, *configs: Dict[str, Any]) -> T:
        """Merge multiple configurations with later ones taking precedence."""
        merged = {}
        
        for config in configs:
            self._deep_update(merged, config)
        
        return self.schema.validate(merged)
    
    @staticmethod
    def _deep_update(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Recursively update dictionary."""
        for key, value in source.items():
            if isinstance(value, dict) and key in target:
                ConfigLoader._deep_update(target[key], value)
            else:
                target[key] = value

def prompt_input(
    prompt: str,
    config: Optional[InputConfig] = None,
    default: Optional[str] = None,
    hide_input: bool = False
) -> str:
    """Prompt for user input with validation."""
    import getpass
    
    cfg = config or InputConfig()
    
    while True:
        try:
            # Add default to prompt if provided
            full_prompt = f"{prompt} "
            if default and not hide_input:
                full_prompt = f"{prompt} [{default}] "
            
            # Get input
            if hide_input:
                value = getpass.getpass(full_prompt)
            else:
                value = input(full_prompt)
            
            # Use default if empty
            if not value and default:
                value = default
            
            return cfg.validate(value)
            
        except ValidationError as e:
            logger.error(str(e))
            if e.details:
                logger.error(e.details)
        except (KeyboardInterrupt, EOFError):
            raise ValidationError(
                message="Input cancelled by user",
                field="input"
            )

def prompt_yes_no(
    prompt: str,
    default: Optional[bool] = None
) -> bool:
    """Prompt for yes/no input."""
    suffix = " [y/n] "
    if default is not None:
        suffix = " [Y/n] " if default else " [y/N] "
    
    while True:
        try:
            value = input(f"{prompt}{suffix}").strip().lower()
            
            if not value and default is not None:
                return default
            
            if value in {'y', 'yes'}:
                return True
            if value in {'n', 'no'}:
                return False
                
            logger.error("Please answer 'yes' or 'no'")
            
        except (KeyboardInterrupt, EOFError):
            raise ValidationError(
                message="Input cancelled by user",
                field="input"
            )

def prompt_choice(
    prompt: str,
    choices: List[str],
    default: Optional[str] = None
) -> str:
    """Prompt for choice from list."""
    if not choices:
        raise ValueError("Choices list cannot be empty")
    
    # Show choices
    print(f"\n{prompt}")
    for i, choice in enumerate(choices, 1):
        print(f"{i}. {choice}")
    
    # Add default to prompt if provided
    input_prompt = "\nEnter number"
    if default:
        if default not in choices:
            raise ValueError("Default value must be in choices")
        default_idx = choices.index(default) + 1
        input_prompt = f"{input_prompt} [{default_idx}]"
    input_prompt = f"{input_prompt}: "
    
    while True:
        try:
            value = input(input_prompt).strip()
            
            # Use default if empty
            if not value and default:
                return default
            
            try:
                index = int(value) - 1
                if 0 <= index < len(choices):
                    return choices[index]
            except ValueError:
                pass
            
            logger.error(
                "Please enter a number between 1 and %d",
                len(choices)
            )
            
        except (KeyboardInterrupt, EOFError):
            raise ValidationError(
                message="Input cancelled by user",
                field="input"
            )

def prompt_path(
    prompt: str,
    must_exist: bool = False,
    create: bool = False,
    default: Optional[Union[str, Path]] = None
) -> Path:
    """Prompt for file path with validation."""
    while True:
        try:
            # Add default to prompt if provided
            full_prompt = prompt
            if default:
                full_prompt = f"{prompt} [{default}]"
            
            value = input(f"{full_prompt}: ").strip()
            
            # Use default if empty
            if not value and default:
                value = str(default)
            
            return validate_path(
                value,
                must_exist=must_exist,
                create=create
            )
            
        except ValidationError as e:
            logger.error(str(e))
            if e.details:
                logger.error(e.details)
        except (KeyboardInterrupt, EOFError):
            raise ValidationError(
                message="Input cancelled by user",
                field="input"
            )

def prompt_filename(
    prompt: str,
    default: Optional[str] = None,
    sanitize: bool = True
) -> str:
    """Prompt for filename with optional sanitization."""
    while True:
        try:
            # Add default to prompt if provided
            full_prompt = prompt
            if default:
                full_prompt = f"{prompt} [{default}]"
            
            value = input(f"{full_prompt}: ").strip()
            
            # Use default if empty
            if not value and default:
                value = default
            
            if not value:
                raise ValidationError(
                    message="Filename cannot be empty",
                    field="filename"
                )
            
            return sanitize_filename(value) if sanitize else value
            
        except ValidationError as e:
            logger.error(str(e))
            if e.details:
                logger.error(e.details)
        except (KeyboardInterrupt, EOFError):
            raise ValidationError(
                message="Input cancelled by user",
                field="input"
            ) 
