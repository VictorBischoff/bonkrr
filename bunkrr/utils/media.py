"""Media utilities for the bunkrr package."""
import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

from ..core.exceptions import ValidationError
from ..core.logger import setup_logger
from .filesystem import get_file_size, safe_remove

logger = setup_logger('bunkrr.media')

# Initialize mimetypes
mimetypes.init()

# Common media extensions
MEDIA_EXTENSIONS: Set[str] = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff',
    # Videos
    '.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv',
    # Archives
    '.zip', '.rar', '.7z', '.tar', '.gz'
}

def get_media_type(filename: str) -> Optional[str]:
    """Get media type from filename."""
    try:
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            return None
            
        main_type = mime_type.split('/')[0]
        if main_type in {'image', 'video', 'application'}:
            return main_type
            
        return None
        
    except Exception as e:
        logger.error("Failed to get media type for %s: %s", filename, str(e))
        return None

def is_media_file(filename: str) -> bool:
    """Check if filename has a media extension."""
    try:
        ext = os.path.splitext(filename)[1].lower()
        return ext in MEDIA_EXTENSIONS
    except Exception as e:
        logger.error("Failed to check media file %s: %s", filename, str(e))
        return False

def extract_filename(url: str) -> Optional[str]:
    """Extract filename from URL."""
    try:
        # Parse URL and get path
        path = urlparse(url).path
        if not path:
            return None
            
        # Get last component and decode
        filename = unquote(os.path.basename(path))
        if not filename:
            return None
            
        # Check if it's a media file
        if not is_media_file(filename):
            return None
            
        return filename
        
    except Exception as e:
        logger.error("Failed to extract filename from %s: %s", url, str(e))
        return None

def calculate_file_hash(path: Path, algorithm: str = 'sha256') -> Optional[str]:
    """Calculate file hash using specified algorithm."""
    if not path.is_file():
        return None
        
    try:
        hasher = hashlib.new(algorithm)
        
        with open(path, 'rb') as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
                
        return hasher.hexdigest()
        
    except Exception as e:
        logger.error("Failed to calculate hash for %s: %s", path, str(e))
        return None

def verify_file_integrity(
    path: Path,
    expected_size: Optional[int] = None,
    expected_hash: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Verify file integrity using size and hash."""
    if not path.is_file():
        return False, "File does not exist"
        
    try:
        # Check file size
        if expected_size is not None:
            actual_size = get_file_size(path)
            if actual_size != expected_size:
                return False, f"Size mismatch: expected {expected_size}, got {actual_size}"
                
        # Check file hash
        if expected_hash is not None:
            actual_hash = calculate_file_hash(path)
            if actual_hash != expected_hash:
                return False, f"Hash mismatch: expected {expected_hash}, got {actual_hash}"
                
        return True, None
        
    except Exception as e:
        logger.error("Failed to verify file %s: %s", path, str(e))
        return False, str(e)

def clean_failed_downloads(path: Path) -> None:
    """Clean up failed or incomplete downloads."""
    try:
        # Remove temporary files
        if path.suffix == '.tmp':
            safe_remove(path)
            return
            
        # Remove empty files
        if path.stat().st_size == 0:
            safe_remove(path)
            return
            
    except Exception as e:
        logger.error("Failed to clean up file %s: %s", path, str(e))

def get_media_info(path: Path) -> Dict[str, any]:
    """Get media file information."""
    if not path.is_file():
        raise ValidationError(f"File does not exist: {path}")
        
    try:
        stat = path.stat()
        
        return {
            'path': str(path),
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'type': get_media_type(path.name),
            'hash': calculate_file_hash(path)
        }
        
    except Exception as e:
        logger.error("Failed to get media info for %s: %s", path, str(e))
        raise ValidationError(f"Failed to get media info: {str(e)}") 
