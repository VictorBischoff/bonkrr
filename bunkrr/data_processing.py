"""Module for processing and downloading media from Bunkr."""
import asyncio
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import unquote, urlparse, urljoin, parse_qs
import io

from aiohttp import (
    ClientSession, 
    ClientTimeout, 
    client_exceptions, 
    TCPConnector,
    ClientResponse,
    TraceConfig
)
from bs4 import BeautifulSoup, SoupStrainer
from fake_useragent import UserAgent
import aiofiles
import aiofiles.os

from .config import DownloadConfig
from .logger import setup_logger, log_exception, log_html_error
from .ui import DownloadProgress

logger = setup_logger('bunkrr.processor')

# Connection pool settings
MAX_CONNECTIONS_PER_HOST = 8
DNS_CACHE_TTL = 300  # 5 minutes
KEEPALIVE_TIMEOUT = 60  # 1 minute
POOL_TIMEOUT = 30  # Pool acquisition timeout

# Request timeouts (in seconds)
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 300  # Longer timeout for downloads
TOTAL_TIMEOUT = 600  # Overall request timeout

# Optimize file I/O with larger buffer sizes
DOWNLOAD_CHUNK_SIZE = 64 * 1024  # 64KB chunks for downloads
WRITE_BUFFER_SIZE = 1024 * 1024  # 1MB write buffer

# File operation helpers
async def write_buffered(file, data: bytes, buffer: io.BytesIO):
    """Write data using a buffer to reduce I/O operations."""
    buffer.write(data)
    if buffer.tell() >= WRITE_BUFFER_SIZE:
        await file.write(buffer.getvalue())
        buffer.seek(0)
        buffer.truncate()

async def flush_buffer(file, buffer: io.BytesIO):
    """Flush remaining data in buffer to file."""
    if buffer.tell() > 0:
        await file.write(buffer.getvalue())
        buffer.seek(0)
        buffer.truncate()

# Optimize parsing by defining strainers for different content types
ALBUM_STRAINER = SoupStrainer(lambda tag, attrs: 
    tag == 'meta' and 'og:title' == attrs.get('property', '') or
    tag == 'h1' and 'truncate' in attrs.get('class', []) or
    tag == 'div' and 'theItem' in attrs.get('class', []) or
    tag == 'a' and 'download' == attrs.get('aria-label', '') or
    tag == 'p' and ('display:none;' == attrs.get('style', '') or 'theSize' in attrs.get('class', [])) or
    tag == 'span' and ('theDate' in attrs.get('class', []) or 'font-semibold' in attrs.get('class', [])) or
    tag == 'img' and 'grid-images_box-img' in attrs.get('class', [])
)
MEDIA_STRAINER = SoupStrainer(['video', 'source', 'img'])

@lru_cache(maxsize=100)
def create_soup(content: str, parser: str = 'lxml', strainer: Optional[SoupStrainer] = None) -> BeautifulSoup:
    """Create BeautifulSoup object with caching and optimized parsing."""
    return BeautifulSoup(content, parser, parse_only=strainer)

class MediaProcessor:
    """Handle media processing and downloading with improved organization."""
    
    # Updated CDN domains with performance optimizations
    CDN_DOMAINS = {  # Changed to set for O(1) lookup
        'media-files.bunkr.site',
        'media-files2.bunkr.site',
        'c.bunkr-cache.se',
        'taquito.bunkr.ru',
        'i-taquito.bunkr.ru',
        'i-burger.bunkr.ru',
        'kebab.bunkr.ru',
        'media-files.bunkr.ru',
        'media-files2.bunkr.ru',
        'media-files.bunkr.ph',
        'media-files2.bunkr.ph'
    }
    
    def __init__(self, config: DownloadConfig):
        self.config = config
        # Enhanced connection pool configuration
        connector = TCPConnector(
            limit=config.max_concurrent_downloads * 2,  # Double the connection pool
            limit_per_host=MAX_CONNECTIONS_PER_HOST,  # Limit connections per host
            ttl_dns_cache=DNS_CACHE_TTL,  # Cache DNS results
            enable_cleanup_closed=True,  # Clean up closed connections
            force_close=False,  # Allow connection reuse
            keepalive_timeout=KEEPALIVE_TIMEOUT,  # Keep connections alive
        )
        
        # Create trace config for connection monitoring
        trace_config = TraceConfig()
        trace_config.on_connection_queued_start.append(self._on_connection_queued_start)
        trace_config.on_connection_queued_end.append(self._on_connection_queued_end)
        trace_config.on_connection_create_start.append(self._on_connection_create_start)
        trace_config.on_connection_create_end.append(self._on_connection_create_end)
        
        self._download_semaphore = asyncio.Semaphore(config.max_concurrent_downloads)
        self._rate_limiter = RateLimiter(config.rate_limit, config.rate_window)
        self._session: Optional[ClientSession] = None
        self._connector = connector
        self._trace_config = trace_config
        self._processed_urls: Set[str] = set()
        self._url_pattern = re.compile(r'/[aif]/([A-Za-z0-9]+)')  # Precompile regex
        self._progress = DownloadProgress()
        
        logger.info(
            "Initialized MediaProcessor",
            extra={
                "max_concurrent_downloads": config.max_concurrent_downloads,
                "rate_limit": config.rate_limit,
                "rate_window": config.rate_window,
                "connection_pool_size": config.max_concurrent_downloads * 2,
                "connections_per_host": MAX_CONNECTIONS_PER_HOST,
                "keepalive_timeout": KEEPALIVE_TIMEOUT
            }
        )
        
    async def __aenter__(self):
        """Set up async context with improved session configuration."""
        if not self._session:
            # Configure timeouts for different operations
            timeout = ClientTimeout(
                total=TOTAL_TIMEOUT,
                connect=CONNECT_TIMEOUT,
                sock_read=READ_TIMEOUT
            )
            
            self._session = ClientSession(
                connector=self._connector,
                timeout=timeout,
                raise_for_status=True,
                trace_configs=[self._trace_config]
            )
            
            logger.debug(
                "Created new ClientSession with timeouts: total=%ds, connect=%ds, read=%ds",
                TOTAL_TIMEOUT,
                CONNECT_TIMEOUT,
                READ_TIMEOUT
            )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources properly with graceful shutdown."""
        if self._session:
            try:
                # Wait for ongoing requests to complete (up to 30 seconds)
                await asyncio.wait_for(self._session.close(), timeout=30)
            except asyncio.TimeoutError:
                logger.warning("Session close timed out, forcing close")
            finally:
                await self._connector.close()
                
        logger.debug("Closed ClientSession and Connector")
        
    # Connection pool monitoring callbacks
    async def _on_connection_queued_start(self, session, trace_config_ctx, params):
        logger.debug("Connection queued: waiting for pool slot")
        
    async def _on_connection_queued_end(self, session, trace_config_ctx, params):
        logger.debug("Connection dequeued: acquired from pool")
        
    async def _on_connection_create_start(self, session, trace_config_ctx, params):
        logger.debug("Creating new connection")
        
    async def _on_connection_create_end(self, session, trace_config_ctx, params):
        logger.debug("New connection created")
        
    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> ClientResponse:
        """Make an HTTP request with automatic retry and connection management."""
        retry_count = 0
        max_retries = self.config.max_retries
        
        while retry_count < max_retries:
            try:
                # Add default headers for better connection handling
                headers = kwargs.get('headers', {})
                headers.update({
                    'Connection': 'keep-alive',
                    'Keep-Alive': f'timeout={KEEPALIVE_TIMEOUT}',
                    'Accept-Encoding': 'gzip, deflate',
                })
                kwargs['headers'] = headers
                
                # Attempt the request
                response = await self._session.request(method, url, **kwargs)
                
                # Update pool metrics
                active_connections = len(self._connector._conns)
                acquired_connections = len(self._connector._acquired)
                logger.debug(
                    "Connection pool status - Active: %d, Acquired: %d",
                    active_connections,
                    acquired_connections
                )
                
                return response
                
            except (client_exceptions.ServerTimeoutError,
                   client_exceptions.ClientConnectorError,
                   client_exceptions.ClientConnectionError,  # Base class
                   client_exceptions.ServerDisconnectedError,
                   client_exceptions.ClientPayloadError,  # Add payload errors
                   client_exceptions.ClientOSError,  # Add OS errors
                   asyncio.TimeoutError) as e:  # Add asyncio timeout
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = self.config.retry_delay * (2 ** (retry_count - 1))
                    logger.warning(
                        "Connection error for %s, retrying in %ds (%d/%d): %s",
                        url, wait_time, retry_count, max_retries, str(e)
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise  # Re-raise the last error
                
    async def _fetch_data(self, url: str, data_type: str) -> Optional[Dict[str, Any]]:
        """Fetch data with improved connection handling."""
        logger.debug("Fetching %s data from: %s", data_type, url)
        
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        headers = {'User-Agent': self._get_random_user_agent(), 'Referer': base_url}
        
        async with self._download_semaphore:  # Limit concurrent requests
            await self._rate_limiter.acquire()
            
            try:
                async with await self._make_request(
                    'GET',
                    url,
                    headers=headers,
                    allow_redirects=True,
                    ssl=False,  # Skip SSL verification for performance
                    timeout=ClientTimeout(
                        total=TOTAL_TIMEOUT,
                        connect=CONNECT_TIMEOUT,
                        sock_read=READ_TIMEOUT
                    )
                ) as response:
                    status = response.status
                    content = await response.text()
                    
                    if status == 200:
                        # Use appropriate strainer based on data type
                        strainer = ALBUM_STRAINER if data_type == "album-info" else MEDIA_STRAINER
                        soup = create_soup(content, 'lxml', strainer)
                        return (await self._parse_album_info(soup, url, base_url) if data_type == "album-info"
                              else await self._parse_media_info(soup, base_url))
                              
                    elif status == 429:  # Rate limit
                        retry_delay = int(response.headers.get('Retry-After', 30))
                        logger.warning("Rate limited, waiting %ds", retry_delay)
                        await asyncio.sleep(retry_delay)
                        return await self._fetch_data(url, data_type)  # Retry
                        
                    # Log error and return None
                    log_html_error(logger, status, url, content)
                    return None
                    
            except Exception as e:
                log_exception(logger, e, f"fetching {data_type}")
                return None

    async def process_album(self, album_url: str, parent_folder: Path) -> Tuple[int, int]:
        """Process a single album URL with optimized batch processing."""
        logger.info("Processing album: %s", album_url)
        
        if not self._session:
            raise RuntimeError("MediaProcessor must be used as an async context manager")
        
        # Extract album ID using precompiled regex
        if not (album_id := self._extract_album_id(album_url)):
            logger.error("Could not extract album ID from URL: %s", album_url)
            return 0, 0
            
        # Fetch and parse album data in parallel with folder creation
        album_info_task = asyncio.create_task(self._fetch_data(album_url, "album-info"))
        
        # Create album folder asynchronously
        album_folder = parent_folder / f"Album_{album_id}"  # Temporary name
        try:
            await asyncio.to_thread(album_folder.mkdir, parents=True, exist_ok=True)
        except Exception as e:
            log_exception(logger, e, "creating album folder")
            return 0, 0
            
        # Wait for album info
        if not (album_info := await album_info_task):
            logger.error("Failed to fetch album info: %s", album_url)
            return 0, 0
            
        # Generate final folder name with proper handling for existing directories
        base_folder_name = self._sanitize_folder_name(album_info['title'])
        final_folder = parent_folder / base_folder_name
        counter = 1
        
        # If target exists, append a number until we find a unique name
        while final_folder.exists():
            new_name = f"{base_folder_name}_{counter}"
            final_folder = parent_folder / new_name
            counter += 1
            
        if album_folder != final_folder:
            try:
                # Use rename for atomic operation if target doesn't exist
                await asyncio.to_thread(album_folder.rename, final_folder)
                album_folder = final_folder
                logger.info("Renamed album folder to: %s", final_folder.name)
            except Exception as e:
                log_exception(logger, e, "renaming album folder")
                logger.warning("Continuing with original folder name: %s", album_folder.name)
                # Continue with original folder name
        
        # Process media in optimized batches
        return await self._download_media_from_urls(
            album_info['media_info'],  # Pass complete media info
            album_folder,
            album_info['title']
        )

    async def _download_media_from_urls(
        self,
        media_info: List[Dict[str, Any]],
        album_folder: Path,
        album_title: str
    ) -> Tuple[int, int]:
        """Download media files from URLs with optimized batching."""
        if not media_info:
            logger.error("No media info provided for download")
            return 0, 0

        total_files = len(media_info)
        chunk_size = min(self.config.max_concurrent_downloads, 10)
        total_chunks = (total_files + chunk_size - 1) // chunk_size

        success_count = 0
        failed_count = 0

        # Initialize progress tracking
        self._progress.update_album(album_title, total_files)
        self._progress.start()

        for chunk_idx in range(total_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, total_files)
            chunk = media_info[start_idx:end_idx]

            logger.debug(
                "Processing chunk %d/%d (%d files)",
                chunk_idx + 1,
                total_chunks,
                len(chunk)
            )

            # Create tasks for concurrent downloads
            tasks = []
            for i, item in enumerate(chunk):
                file_url = item['url']
                # Use original filename if available, otherwise generate one
                filename = item.get('filename') or f"{start_idx+i:04d}_{Path(urlparse(file_url).path).name}"
                
                # Skip if file exists and is valid
                file_path = album_folder / filename
                if file_path.exists() and file_path.stat().st_size > 0:
                    logger.debug("Skipping existing file: %s", filename)
                    success_count += 1
                    self._progress.update_progress(advance=1)
                    continue

                tasks.append(
                    asyncio.create_task(
                        self._download_file(
                            file_url,
                            file_path
                        )
                    )
                )

            if tasks:
                # Wait for all tasks in chunk to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("Download failed: %s", str(result))
                        failed_count += 1
                        self._progress.update_progress(advance=1, failed=True)
                    elif isinstance(result, tuple):
                        success, size = result
                        if success:
                            success_count += 1
                            self._progress.update_progress(advance=1, downloaded=size)
                        else:
                            failed_count += 1
                            self._progress.update_progress(advance=1, failed=True)

            # Add delay between chunks based on rate limit
            if chunk_idx < total_chunks - 1:
                delay = self.config.rate_window / self.config.rate_limit
                logger.debug("Waiting %.2fs before next chunk", delay)
                await asyncio.sleep(delay)

        # Stop progress tracking and show summary
        self._progress.stop()
        return success_count, failed_count

    async def _download_file(
        self,
        url: str,
        file_path: Path
    ) -> Tuple[bool, int]:
        """Download a single file with improved error handling and I/O optimization."""
        temp_path = file_path.with_suffix('.part')
        retry_count = 0
        max_retries = self.config.max_retries
        write_buffer = io.BytesIO()
        
        while retry_count < max_retries:
            try:
                # First get the direct download URL
                download_url = await self._get_download_url(url)
                if not download_url:
                    logger.error("Failed to get download URL for: %s", url)
                    return False, 0

                headers = {
                    'User-Agent': self._get_random_user_agent(),
                    'Accept': '*/*',
                    'Accept-Encoding': 'identity',
                    'Referer': 'https://bunkr.site/'
                }

                async with self._download_semaphore:
                    await self._rate_limiter.acquire()
                    
                    async with self._session.get(
                        download_url,
                        headers=headers,
                        allow_redirects=True,
                        ssl=False  # Skip SSL verification for performance
                    ) as response:
                        if response.status == 429:
                            retry_count += 1
                            retry_after = int(response.headers.get('Retry-After', self.config.retry_delay))
                            logger.warning(
                                "Rate limit hit for %s, waiting %ds (retry %d/%d)",
                                file_path.name,
                                retry_after,
                                retry_count,
                                max_retries
                            )
                            await asyncio.sleep(retry_after)
                            continue

                        if response.status != 200:
                            logger.error(
                                "Failed to download %s: HTTP %d",
                                download_url,
                                response.status
                            )
                            if retry_count < max_retries - 1:
                                retry_count += 1
                                await asyncio.sleep(self.config.retry_delay)
                                continue
                            return False, 0

                        # Get content length for size verification
                        content_length = int(response.headers.get('content-length', 0))
                        if content_length < self.config.min_file_size:
                            logger.error(
                                "Content length too small: %s (%d bytes)",
                                file_path.name,
                                content_length
                            )
                            return False, 0

                        # Check content type
                        content_type = response.headers.get('content-type', '')
                        if 'text/html' in content_type:
                            logger.error(
                                "Received HTML instead of file: %s",
                                download_url
                            )
                            return False, 0

                        # Open file in append mode if it exists and is incomplete
                        mode = 'ab' if temp_path.exists() else 'wb'
                        downloaded_size = 0
                        
                        # Use buffered writes for better I/O performance
                        async with aiofiles.open(temp_path, mode, buffering=WRITE_BUFFER_SIZE) as f:
                            async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                                if asyncio.current_task().cancelled():
                                    logger.info("Download cancelled: %s", file_path.name)
                                    raise asyncio.CancelledError()
                                await write_buffered(f, chunk, write_buffer)
                                downloaded_size += len(chunk)
                            # Flush any remaining data
                            await flush_buffer(f, write_buffer)

                        # If we got here, the download was successful
                        break

            except asyncio.CancelledError:
                logger.info("Download cancelled: %s", file_path.name)
                if temp_path.exists():
                    await aiofiles.os.remove(temp_path)
                raise
            except Exception as e:
                log_exception(logger, e, f"downloading {url}")
                if retry_count < max_retries - 1:
                    retry_count += 1
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                if temp_path.exists():
                    await aiofiles.os.remove(temp_path)
                return False, 0

        # Verify download
        try:
            file_size = (await aiofiles.os.stat(temp_path)).st_size
            if file_size < self.config.min_file_size:
                logger.error(
                    "Downloaded file too small: %s (%d bytes)",
                    file_path.name,
                    file_size
                )
                await aiofiles.os.remove(temp_path)
                return False, 0
        except Exception as e:
            log_exception(logger, e, f"verifying file size for {file_path.name}")
            if temp_path.exists():
                await aiofiles.os.remove(temp_path)
            return False, 0

        # Rename temp file to final name using async rename
        try:
            await aiofiles.os.rename(temp_path, file_path)
        except Exception as e:
            log_exception(logger, e, f"renaming {temp_path} to {file_path}")
            if temp_path.exists():
                await aiofiles.os.remove(temp_path)
            return False, 0
            
        return True, downloaded_size

    def _get_random_user_agent(self) -> str:
        """Get a random user agent string."""
        try:
            ua = UserAgent()
            agent = ua.random
            logger.debug("Generated random user agent: %s", agent)
            return agent
        except Exception as e:
            log_exception(logger, e, "user agent generation")
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
    def _extract_album_id(self, url: str) -> Optional[str]:
        """Extract album ID using precompiled regex."""
        if match := self._url_pattern.search(url):
            album_id = match.group(1)
            logger.debug("Extracted album ID: %s", album_id)
            return album_id
        logger.error("No matching pattern found for URL: %s", url)
        return None
        
    async def _parse_album_info(self, soup: BeautifulSoup, url: str, base_url: str) -> Optional[Dict[str, Any]]:
        """Parse album information from HTML with optimized selectors."""
        logger.debug("Parsing album info from HTML")
        
        # Get album title from meta tag or h1 using optimized selectors
        title = None
        meta_title = soup.find('meta', property='og:title', attrs={'content': True})
        if meta_title:
            title = meta_title['content']
            logger.debug("Found title from meta: %s", title)
        else:
            h1_title = soup.find('h1', class_='truncate')
            if h1_title:
                title = h1_title.get_text(strip=True)
                logger.debug("Found title from h1: %s", title)
        
        if not title:
            album_id = self._extract_album_id(url) or url.split('/')[-1]
            title = f"Album_{album_id}"
            logger.debug("Using fallback title: %s", title)
        
        # Get album stats if available using optimized selector
        stats_text = soup.find('span', class_='font-semibold')
        if stats_text:
            logger.debug("Album stats: %s", stats_text.get_text(strip=True))
        
        # Find all media items in the grid using optimized selectors
        media_links = set()
        media_info = []
        
        # Use CSS selector for better performance
        for item in soup.select('div.theItem'):
            try:
                # Get download link with optimized selector
                download_link = item.find('a', attrs={'aria-label': 'download', 'href': True})
                if not download_link:
                    continue
                    
                href = download_link['href']
                # Convert relative URL to absolute
                if href.startswith('/'):
                    href = f"{base_url}{href}"
                    
                # Get file info with optimized selectors
                filename = item.find('p', style='display:none;')
                filename = filename.get_text(strip=True) if filename else ''
                
                size_elem = item.find('p', class_='theSize')
                size = size_elem.get_text(strip=True) if size_elem else ''
                
                date_elem = item.find('span', class_='theDate')
                date = date_elem.get_text(strip=True) if date_elem else ''
                
                thumbnail = item.find('img', class_='grid-images_box-img', attrs={'src': True})
                thumbnail_url = thumbnail['src'] if thumbnail else None
                
                media_info.append({
                    'url': href,
                    'filename': filename,
                    'size': size,
                    'date': date,
                    'thumbnail': thumbnail_url
                })
                
                media_links.add(href)
                logger.debug("Found media item: %s (%s)", filename, size)
                
            except Exception as e:
                log_exception(logger, e, "parsing media item")
                continue
        
        if not media_links:
            logger.error("No media links found in album: %s", url)
            log_html_error(
                logger,
                0,
                url,
                str(soup),
                error_details={
                    'title': title,
                    'error_message': None,
                    'status_code': 0,
                    'url': url,
                    'error': 'No media links found'
                }
            )
            return None
            
        logger.info("Found %d unique media items in album", len(media_links))
        return {
            'title': title,
            'url': url,
            'media_links': list(media_links),
            'media_info': media_info
        }
        
    async def _parse_media_info(self, soup: BeautifulSoup, base_url: str) -> Optional[Dict[str, Any]]:
        """Parse media information from HTML with optimized selectors."""
        logger.debug("Parsing media info from HTML")
        download_url = None
        
        # Try to find video source with optimized selectors
        video = soup.find('video')
        if video:
            # Try source tag first with optimized selector
            source = video.find('source', attrs={'src': True})
            if source:
                download_url = source['src']
                logger.debug("Found video source: %s", download_url)
            # Try direct video src
            elif 'src' in video.attrs:
                download_url = video['src']
                logger.debug("Found direct video src: %s", download_url)
        
        # Try to find image source with optimized selector
        if not download_url:
            img = soup.find('img', class_='max-h-full', attrs={'src': True})
            if img:
                download_url = img['src']
                logger.debug("Found image source: %s", download_url)
        
        if download_url:
            return {'download_url': download_url}
        
        logger.error("No download URL found in media page")
        # Save the HTML for debugging
        log_html_error(
            logger,
            0,  # Not an HTTP error
            base_url,
            str(soup),
            error_details={'error': 'No download URL found'}
        )
        return None
            
    async def _get_download_url(self, file_url: str) -> Optional[str]:
        """Get the actual download URL from a file page with improved extraction."""
        try:
            parsed = urlparse(file_url)
            path_parts = parsed.path.strip('/').split('/')
            
            # Direct file URL pattern
            if 'f' in path_parts:
                file_id = path_parts[path_parts.index('f') + 1]
                if not file_id:
                    return None
                    
                # Try different CDN domains in order of preference
                cdn_domains = [
                    'https://c.bunkr-cache.se',
                    'https://taquito.bunkr.ru',
                    'https://i-taquito.bunkr.ru',
                    'https://i-burger.bunkr.ru'
                ]
                
                # Try each CDN domain
                for cdn in cdn_domains:
                    try:
                        test_url = f"{cdn}/{file_id}"
                        async with self._session.head(test_url, allow_redirects=True, timeout=5) as response:
                            if response.status == 200:
                                logger.info(f"Found working CDN: {cdn}")
                                return test_url
                    except Exception as e:
                        logger.debug(f"CDN {cdn} failed: {str(e)}")
                        continue
                        
                # If no CDN works, try to fetch the page and look for direct links
                try:
                    media_info = await self._fetch_data(file_url, "media-info")
                    if media_info and media_info.get('download_url'):
                        return media_info['download_url']
                except Exception as e:
                    logger.debug(f"Failed to fetch media info: {str(e)}")
                    
                # Default to i-burger if nothing else works
                logger.warning("Defaulting to i-burger CDN")
                return f"https://i-burger.bunkr.ru/{file_id}"
                
            # Download URL pattern
            if 'd' in path_parts:
                file_id = path_parts[path_parts.index('d') + 1]
                if not file_id:
                    return None
                return f"https://cdn.bunkr.ru/{file_id}"
                
            logger.warning(f"Could not determine download URL format: {file_url}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting download URL: {str(e)}")
            return None
            
    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        """Sanitize folder name by removing invalid characters."""
        # Remove invalid characters
        name = ''.join(c for c in name if c not in '<>:"/\\|?*')
        # Remove leading/trailing spaces and dots
        name = name.strip('. ')
        # Limit length
        return name[:255]
        
class RateLimiter:
    """Efficient rate limiter using asyncio primitives and sliding window."""
    
    def __init__(self, rate_limit: int, window_size: int):
        self.rate_limit = rate_limit
        self.window_size = window_size
        self._window = asyncio.Queue(maxsize=rate_limit)
        self._lock = asyncio.Lock()
        
    async def acquire(self):
        """Acquire a rate limit token using sliding window algorithm."""
        async with self._lock:
            now = datetime.now().timestamp()
            
            # Remove expired timestamps
            while not self._window.empty():
                try:
                    timestamp = self._window.get_nowait()
                    if now - timestamp <= self.window_size:
                        # Put it back if still valid
                        await self._window.put(timestamp)
                        break
                except asyncio.QueueEmpty:
                    break
            
            # Check if we can add a new request
            if self._window.qsize() < self.rate_limit:
                await self._window.put(now)
                return
            
            # Calculate wait time based on oldest timestamp
            try:
                oldest = self._window.get_nowait()
                wait_time = max(0, self.window_size - (now - oldest))
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                # Add current request timestamp
                await self._window.put(now)
            except asyncio.QueueEmpty:
                # Queue is empty, we can proceed
                await self._window.put(now)
                
    async def reset(self):
        """Reset the rate limiter state."""
        async with self._lock:
            while not self._window.empty():
                try:
                    self._window.get_nowait()
                except asyncio.QueueEmpty:
                    break
