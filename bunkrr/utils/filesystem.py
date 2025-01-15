"""Filesystem utilities for the bunkrr package."""
import os
import shutil
from pathlib import Path
from typing import Optional

from ..core.exceptions import FileSystemError
from ..core.logger import setup_logger

logger = setup_logger('bunkrr.filesystem')

def ensure_directory(path: Path) -> None:
    """Ensure directory exists and is writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        if not os.access(path, os.W_OK):
            raise FileSystemError(f"Directory not writable: {path}")
    except Exception as e:
        raise FileSystemError(f"Failed to create directory: {path}", str(e))

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for filesystem."""
    # Remove invalid characters
    safe_name = "".join(c for c in filename if c.isalnum() or c in "- _.")
    # Remove leading/trailing spaces and dots
    safe_name = safe_name.strip(". ")
    # Ensure filename is not empty
    if not safe_name:
        safe_name = "unnamed"
    return safe_name[:255]  # Limit length

def get_unique_path(path: Path) -> Path:
    """Get unique path by appending number if needed."""
    if not path.exists():
        return path
        
    parent = path.parent
    stem = path.stem
    suffix = path.suffix if not path.is_dir() else ""
    counter = 1
    
    # If it's a directory and empty, return it
    if path.is_dir() and not any(path.iterdir()):
        return path
    
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1

def safe_move(src: Path, dst: Path) -> None:
    """Safely move file with proper error handling."""
    try:
        # Ensure destination directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)
        
        # Get unique destination path
        dst = get_unique_path(dst)
        
        # Move file
        shutil.move(str(src), str(dst))
        logger.debug("Moved file: %s -> %s", src, dst)
        
    except Exception as e:
        raise FileSystemError(f"Failed to move file: {src} -> {dst}", str(e))

def safe_remove(path: Path) -> None:
    """Safely remove file with proper error handling."""
    try:
        if path.exists():
            path.unlink()
            logger.debug("Removed file: %s", path)
    except Exception as e:
        raise FileSystemError(f"Failed to remove file: {path}", str(e))

def get_file_size(path: Path) -> Optional[int]:
    """Get file size with proper error handling."""
    try:
        return path.stat().st_size if path.exists() else None
    except Exception as e:
        logger.error("Failed to get file size: %s - %s", path, str(e))
        return None

def is_valid_path(path: Path) -> bool:
    """Check if path is valid and accessible."""
    try:
        # Check if path exists
        if not path.exists():
            return True  # Non-existent paths are valid for creation
            
        # Check if directory
        if path.is_dir():
            return os.access(path, os.W_OK)
            
        # Check if file
        return os.access(path.parent, os.W_OK)
        
    except Exception as e:
        logger.error("Error checking path: %s - %s", path, str(e))
        return False 
