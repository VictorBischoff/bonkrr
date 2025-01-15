# Bunkrr Project Overview

## Project Description
Bunkrr is a high-performance media downloader application designed to efficiently download media files from Bunkr.site. The application features a modern terminal user interface, robust error handling, and optimized concurrent downloads.

## Core Features
- Asynchronous media downloads with rate limiting
- Smart retry logic with exponential backoff
- Real-time progress tracking with rich terminal UI
- Concurrent download management
- Automatic file organization
- Comprehensive error handling and logging
- Optimized URL validation with caching

## Technical Architecture

### Core Components
1. **Core (`core/`)**
   - Configuration management (`config.py`)
   - Error handling system (`error_handler.py`, `exceptions.py`)
   - Logging utilities (`logger.py`)

2. **Downloader (`downloader/`)**
   - Download management (`downloader.py`)
   - Rate limiting (`rate_limiter.py`)
   - Connection pooling and session management

3. **Scrapy Integration (`scrapy/`)**
   - Media processing (`processor.py`)
   - Custom pipelines (`pipelines.py`)
   - Middleware components (`middlewares.py`)
   - Spider implementations (`spiders/`)

4. **User Interface (`ui/`)**
   - Console interface (`console.py`)
   - Theme management (`themes.py`)
   - Progress tracking (`progress.py`)

5. **Utilities (`utils/`)**
   - Input validation (`input.py`)
   - Filesystem operations (`filesystem.py`)
   - HTTP utilities (`http.py`)
   - Formatting helpers (`formatting.py`)

### Error Handling System
1. **Exception Hierarchy**
   - `BunkrrError` - Base exception class
   - Specialized exceptions for different error types:
     - `ConfigError` - Configuration issues
     - `ValidationError` - Input validation failures
     - `DownloadError` - Download-related problems
     - `RateLimitError` - Rate limiting issues
     - `FileSystemError` - File operations
     - `ScrapyError` - Scrapy integration
     - `HTTPError` - HTTP communication

2. **Error Handler**
   - Centralized error handling through `ErrorHandler` class
   - Consistent error logging and reporting
   - Error context tracking and preservation
   - Structured error information collection

3. **Error Decorators**
   - `@handle_errors` - For synchronous functions
   - `@handle_async_errors` - For asynchronous functions
   - Automatic error wrapping and context tracking
   - Configurable error reraising

4. **Error Reporting**
   - Detailed error messages with context
   - Structured error information in logs
   - Error code categorization
   - Stack trace preservation

### Performance Features
- Concurrent downloads (max 6 simultaneous)
- Efficient rate limiting with sliding window algorithm (5 requests per 60s window)
- Optimized connection pooling with per-host limits
- DNS result caching (5 minute TTL)
- Smart CDN selection with fallback
- Chunk-based downloads (64KB chunks)
- Buffered file writes (1MB buffer)
- Optimized HTML parsing with lxml and strainers
- BeautifulSoup result caching
- URL validation caching (1024 entries)
- Pre-compiled regex patterns
- Granular timeout management:
  - Connect: 30s
  - Read: 300s
  - Total: 600s
- Connection keep-alive (60s timeout)
- Connection monitoring and metrics

### File Management
- Unique folder name generation
- Atomic file operations
- Temporary file handling
- Download resumption
- File integrity verification

## Development Guidelines

### Code Style
- Type hints for better code clarity
- Comprehensive docstrings
- Consistent error handling patterns
- Clear logging practices

### Best Practices
- Asynchronous operations for I/O
- Resource cleanup in context managers
- Proper exception handling
- Performance optimization
- Security considerations
- Pre-compiled regex patterns
- Efficient data structures (sets, LRU caches)

### Error Handling Best Practices
1. **Use Appropriate Exception Types**
   - Choose specific exception types for different error scenarios
   - Include relevant context information
   - Provide clear error messages

2. **Error Decorator Usage**
   ```python
   @handle_errors(target_error=DownloadError, context='download_operation')
   def download_file(url: str) -> bool:
       # Function implementation
       pass

   @handle_async_errors(target_error=HTTPError, context='api_request')
   async def make_request(url: str) -> dict:
       # Async function implementation
       pass
   ```

3. **Manual Error Handling**
   ```python
   try:
       # Operation that might fail
       pass
   except Exception as e:
       ErrorHandler.handle_error(
           FileSystemError("Operation failed", path=str(path)),
           context="file_operation"
       )
   ```

### Testing
- Unit tests for core functionality
- Integration tests for download flows
- Error scenario testing
- Performance benchmarking
- URL validation test suite

## Future Improvements
1. Enhanced error recovery mechanisms
2. Additional CDN support
3. Download queue management
4. Bandwidth throttling options
5. Extended file format support
6. Advanced filtering capabilities 
