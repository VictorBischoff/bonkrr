"""User input handling and validation with improved organization and error handling."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, ClassVar, Pattern
from urllib.parse import urlparse, unquote
import re
from re import compile as re_compile

from yarl import URL
from rich.console import Console
from rich.prompt import Prompt, Confirm

from .config import DownloadConfig
from .logger import setup_logger

logger = setup_logger('bunkrr.input')
console = Console()

@dataclass
class URLValidationResult:
    """Structure for URL validation results."""
    is_valid: bool
    error_message: Optional[str] = None
    normalized_url: Optional[str] = None

class URLValidator:
    """Handle URL validation with clear rules and better organization."""
    
    # Pre-compile regex patterns for better performance
    _PROTOCOL_PATTERN: ClassVar[Pattern] = re_compile(r'^(?:https?://)?')
    _SUBDOMAIN_PATTERN: ClassVar[Pattern] = re_compile(
        r'^(?:(?:www|cdn|media-files|media-files2|i-burger|i-taquito|c\.bunkr-cache|taquito|kebab)\.)?$'
    )
    _PATH_PATTERN: ClassVar[Pattern] = re_compile(
        r'^/(?:a|album|albums|f|d|v|i)/[a-zA-Z0-9_-]{3,30}(?:/[a-zA-Z0-9_-]*)?/?$'
    )
    _ID_PATTERN: ClassVar[Pattern] = re_compile(r'^[a-zA-Z0-9_-]{3,30}$')
    _TITLE_PATTERN: ClassVar[Pattern] = re_compile(r'(?:/[a-zA-Z0-9_-]*)?/?$')
    
    def __init__(self, config: Optional[DownloadConfig] = None):
        self.config = config or DownloadConfig()
        self.allowed_domains = {d.lstrip('.') for d in self.config.valid_domains}
        domains = '|'.join(re.escape(d) for d in self.allowed_domains)
        self._DOMAIN_PATTERN = re_compile(fr'(?:^|\.)bunkr\.(?:{domains})$')
        logger.debug("Initialized URL validator with allowed domains: %s", self.allowed_domains)
    
    @lru_cache(maxsize=1024)
    def validate(self, url: str) -> URLValidationResult:
        """Validate and normalize a URL with detailed error reporting."""
        # Check for empty URL
        if not url.strip():
            return URLValidationResult(is_valid=False, error_message="Invalid URL format")

        # Handle non-URL strings
        if ' ' in url or not any(c in url for c in ['/', '.']):
            return URLValidationResult(is_valid=False, error_message="Invalid URL format")

        try:
            # Handle protocol-less URLs
            if not url.startswith(('http://', 'https://')):
                url = f'https://{url}'

            # Use yarl's URL parsing
            try:
                parsed_url = URL(url)
                if not parsed_url.host:
                    return URLValidationResult(is_valid=False, error_message="Invalid URL format")
            except Exception:
                return URLValidationResult(is_valid=False, error_message="Invalid URL format")

            # Validate domain
            if not self._validate_domain(parsed_url):
                return URLValidationResult(is_valid=False, error_message="Not a valid Bunkr domain")

            # Validate subdomain
            if not self._validate_subdomain(parsed_url):
                return URLValidationResult(is_valid=False, error_message="Invalid subdomain")

            # Extract and validate ID first
            try:
                path_segments = [seg for seg in parsed_url.path.split('/') if seg]
                type_idx = path_segments.index(next(t for t in path_segments if t in {'a', 'album', 'albums', 'f', 'd', 'v', 'i'}))
                if len(path_segments) <= type_idx + 1:
                    return URLValidationResult(is_valid=False, error_message="URL doesn't match expected Bunkr format")
                raw_id = path_segments[type_idx + 1]
                decoded_id = unquote(raw_id)
                if not self._ID_PATTERN.match(decoded_id):
                    return URLValidationResult(is_valid=False, error_message="Invalid ID format")
            except (StopIteration, IndexError):
                return URLValidationResult(is_valid=False, error_message="URL doesn't match expected Bunkr format")

            # Validate full path format
            if not self._validate_path(parsed_url):
                return URLValidationResult(is_valid=False, error_message="URL doesn't match expected Bunkr format")

            # Create normalized URL
            normalized = self._normalize_url(parsed_url)
            logger.debug("Normalized URL: %s -> %s", url, normalized)
            
            return URLValidationResult(is_valid=True, normalized_url=normalized)

        except Exception as e:
            logger.error("URL validation error: %s", str(e))
            return URLValidationResult(
                is_valid=False,
                error_message="Invalid URL format"
            )

    def _validate_domain(self, url: URL) -> bool:
        """Validate the domain using optimized pattern matching."""
        hostname = url.host
        if not hostname or 'bunkr' not in hostname:
            return False
        return bool(self._DOMAIN_PATTERN.search(hostname))

    def _validate_subdomain(self, url: URL) -> bool:
        """Validate the subdomain using pattern matching."""
        hostname = url.host
        subdomain = hostname.split('bunkr.')[0] if 'bunkr.' in hostname else ''
        return bool(self._SUBDOMAIN_PATTERN.match(subdomain))

    def _validate_path(self, url: URL) -> bool:
        """Validate the URL path using pattern matching."""
        return bool(self._PATH_PATTERN.match(url.path))

    def _validate_id(self, url: URL) -> bool:
        """Extract and validate the resource ID."""
        path_segments = [seg for seg in url.path.split('/') if seg]
        try:
            type_idx = path_segments.index(next(t for t in path_segments if t in {'a', 'album', 'albums', 'f', 'd', 'v', 'i'}))
            raw_id = path_segments[type_idx + 1]
        except (StopIteration, IndexError):
            return False

        decoded_id = unquote(raw_id)
        return bool(self._ID_PATTERN.match(decoded_id))

    def _normalize_url(self, url: URL) -> str:
        """Create a normalized URL from the parsed URL."""
        path_segments = [seg for seg in url.path.split('/') if seg]
        type_idx = path_segments.index(next(t for t in path_segments if t in {'a', 'album', 'albums', 'f', 'd', 'v', 'i'}))
        resource_type = path_segments[type_idx]
        resource_id = path_segments[type_idx + 1]
        
        # Keep original URL format (don't convert /a/ to /album/)
        return str(url.with_path(f'/{resource_type}/{resource_id}'))

class InputHandler:
    """Handle user input with better organization and error handling."""

    def __init__(self, config: Optional[DownloadConfig] = None):
        self.config = config or DownloadConfig()
        self.validator = URLValidator(self.config)

    async def get_urls(self) -> List[str]:
        """Get and validate URLs from user input."""
        while True:
            input_method = Prompt.ask(
                "How would you like to input URLs?",
                choices=["urls", "file"],
                default="urls"
            )

            urls = await self._get_urls_from_input(input_method)
            if urls:
                return urls

            if not Confirm.ask("No valid URLs found. Would you like to try again?"):
                return []

    async def _get_urls_from_input(self, method: str) -> List[str]:
        """Process URLs based on input method."""
        if method == "file":
            return await self._process_url_file()
        return await self._process_direct_input()

    async def _process_url_file(self) -> List[str]:
        """Process URLs from a file with better error handling."""
        filepath = Path(Prompt.ask("Enter the path to your URL file"))
        
        try:
            if not filepath.exists():
                console.print(f"[red]File not found: {filepath}[/red]")
                return []

            content = filepath.read_text(encoding='utf-8')
            return self._validate_urls(content.splitlines())

        except Exception as e:
            logger.error(f"Error reading file: {str(e)}")
            console.print(f"[red]Error reading file: {str(e)}[/red]")
            return []

    async def _process_direct_input(self) -> List[str]:
        """Process directly input URLs."""
        console.print("\n[cyan]Enter Bunkr album URLs[/cyan]")
        console.print("[dim]Format: https://bunkr.site/a/ALBUMID[/dim]")
        console.print("[dim]Multiple URLs can be separated by commas or newlines[/dim]")
        
        urls = Prompt.ask("URLs")
        return self._validate_urls(urls.replace(',', '\n').splitlines())

    def _validate_urls(self, urls: List[str]) -> List[str]:
        """Validate a list of URLs with detailed feedback."""
        valid_urls = []
        invalid_urls = []

        for url in urls:
            url = url.strip()
            if not url:
                continue

            result = self.validator.validate(url)
            if result.is_valid and result.normalized_url:
                valid_urls.append(result.normalized_url)
            else:
                invalid_urls.append((url, result.error_message))

        # Report invalid URLs
        if invalid_urls:
            console.print("\n[yellow]The following URLs were skipped:[/yellow]")
            for url, error in invalid_urls:
                console.print(f"[yellow]- {url}: {error}[/yellow]")

        return valid_urls

    def get_download_folder(self) -> Optional[Path]:
        """Get and validate download folder path."""
        while True:
            folder = Path(Prompt.ask(
                "Enter download folder path",
                default=str(Path.cwd() / "downloads")
            )).expanduser()

            try:
                # Create folder if it doesn't exist
                folder.mkdir(parents=True, exist_ok=True)
                return folder

            except Exception as e:
                logger.error(f"Error creating folder: {str(e)}")
                console.print(f"[red]Error creating folder: {str(e)}[/red]")
                
                if not Confirm.ask("Would you like to try a different folder?"):
                    return None


