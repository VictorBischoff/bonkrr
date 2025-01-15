"""User input handling and validation with improved organization and error handling."""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
import re

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
    
    def __init__(self, config: Optional[DownloadConfig] = None):
        self.config = config or DownloadConfig()
        # Create regex pattern with domains from config
        domains = '|'.join(d.lstrip('.') for d in self.config.valid_domains)
        self.URL_PATTERN = re.compile(
            r'^(?P<protocol>https?://)?'  # Optional protocol
            r'(?:(?P<subdomain>www|cdn|media-files|media-files2|i-burger|i-taquito|c\.bunkr-cache|taquito|kebab)\.)?'  # Optional subdomains
            fr'bunkr\.(?P<domain>{domains})'  # Domain from config
            r'/(?P<type>a|album|albums|f|d|v|i)/'  # Album or file prefix
            r'(?P<id>[a-zA-Z0-9-_]+)'  # Album/file ID
            r'(?:/(?P<title>[^/]+))?'  # Optional title
            r'/?$'  # Optional trailing slash
        )
        logger.debug("Initialized URL validator with pattern: %s", self.URL_PATTERN.pattern)

    def validate(self, url: str) -> URLValidationResult:
        """Validate and normalize a URL with detailed error reporting."""
        try:
            # Add protocol if missing
            if not url.startswith(('http://', 'https://')):
                url = f'https://{url}'

            # Basic URL parsing
            parsed = urlparse(url)
            if not parsed.netloc:
                return URLValidationResult(
                    is_valid=False,
                    error_message="Invalid URL format"
                )

            # Check domain
            domain_parts = parsed.netloc.split('.')
            if len(domain_parts) < 2 or 'bunkr' not in domain_parts:
                return URLValidationResult(
                    is_valid=False,
                    error_message="Not a valid Bunkr domain"
                )

            # Check against pattern
            match = self.URL_PATTERN.match(url)
            if not match:
                return URLValidationResult(
                    is_valid=False,
                    error_message="URL doesn't match expected Bunkr format"
                )

            # Keep original URL format (don't convert /a/ to /album/)
            normalized = self._normalize_url(match)
            logger.debug("Normalized URL: %s -> %s", url, normalized)
            
            return URLValidationResult(
                is_valid=True,
                normalized_url=normalized
            )

        except Exception as e:
            logger.error(f"URL validation error: {str(e)}")
            return URLValidationResult(
                is_valid=False,
                error_message=f"Validation error: {str(e)}"
            )

    @staticmethod
    def _normalize_url(match: re.Match) -> str:
        """Create a normalized URL from regex match."""
        parts = {
            'protocol': match.group('protocol') or 'https://',
            'subdomain': match.group('subdomain') + '.' if match.group('subdomain') else '',
            'domain': f"bunkr.{match.group('domain')}",
            'type': match.group('type'),  # Keep original type (a, album, f, etc.)
            'id': match.group('id')
        }
        return f"{parts['protocol']}{parts['subdomain']}{parts['domain']}/{parts['type']}/{parts['id']}"

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


