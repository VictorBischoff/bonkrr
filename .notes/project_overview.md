"""# Bunkrr Project Overview

## Project Description
Bunkrr is a high-performance media downloader application designed to efficiently download media files from Bunkr.site. The application features a modern terminal user interface, comprehensive error handling, and optimized concurrent downloads.

## Core Features
- Asynchronous media downloads with intelligent rate limiting
- Smart retry logic with exponential backoff
- Real-time progress tracking with rich terminal UI
- Concurrent download management
- Automatic file organization
- Comprehensive error handling and logging
- Optimized URL validation with caching
- Centralized configuration management

## Technical Architecture

### Core Components
1. **Core (`core/`)**
   - Configuration management (`config.py`)
     - Centralized settings with validation
     - Integrated Scrapy configuration
     - Environment-aware defaults
   - Error handling system (`error_handler.py`, `exceptions.py`)
     - Comprehensive exception hierarchy
     - Centralized error handling
     - Context-aware error tracking
   - Logging utilities (`logger.py`)
     - Structured logging
     - Rotating file handlers
     - Contextual error reporting

2. **Downloader (`downloader/`)**
   - Download management (`downloader.py`)
     - Concurrent download handling
     - Retry mechanisms
     - Progress tracking
   - Rate limiting (`rate_limiter.py`)
     - Leaky bucket algorithm
     - Configurable windows
     - Thread-safe operations

3. **Scrapy Integration (`scrapy/`)**
   - Media processing (`processor.py`)
     - Efficient media extraction
     - Pipeline integration
   - Custom pipelines (`pipelines.py`)
     - File handling
     - Error recovery
   - Middleware components (`middlewares.py`)
     - Rate limiting integration
     - Error handling
   - Spider implementations (`spiders/`)
     - Album parsing
     - Media discovery

4. **User Interface (`ui/`)**
   - Console interface (`console.py`)
     - Rich terminal output
     - Interactive prompts
   - Theme management (`themes.py`)
     - Consistent styling
     - Color schemes
   - Progress tracking (`progress.py`)
     - Real-time updates
     - Statistics display

5. **Utilities (`utils/`)**
   - Input validation (`input.py`)
     - URL validation
     - Path checking
   - Filesystem operations (`filesystem.py`)
     - Safe file handling
     - Path management
   - HTTP utilities (`http.py`)
     - Connection pooling
     - Request handling
   - Formatting helpers (`formatting.py`)
     - Text formatting
     - Progress display
   - Media utilities (`media.py`)
     - File type detection
     - Integrity checking
   - Statistics tracking (`stats.py`)
     - Performance metrics
     - Operation tracking
   - Caching utilities (`caching.py`)
     - Memory caching
     - Disk caching
   - Concurrency utilities (`concurrency.py`)
     - Async operations
     - Thread management

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
- Safe file cleanup

## Development Guidelines

### Code Style
- Type hints for better code clarity
- Comprehensive docstrings
- Consistent error handling patterns
- Clear logging practices
- Modular design

### Best Practices
1. **Error Handling**
   - Use appropriate exception types
   - Include context information
   - Apply error decorators consistently
   - Log errors with sufficient detail

2. **Performance**
   - Use async operations for I/O
   - Implement caching where beneficial
   - Pre-compile regular expressions
   - Pool and reuse connections

3. **Resource Management**
   - Use context managers
   - Clean up resources properly
   - Handle interruptions gracefully
   - Monitor resource usage

4. **Security**
   - Validate all inputs
   - Handle sensitive data carefully
   - Use safe file operations
   - Implement rate limiting

### Testing
- Unit tests for core functionality
- Integration tests for download flows
- Error scenario testing
- Performance benchmarking
- URL validation test suite
- Mock external services

## Future Improvements
1. Enhanced error recovery mechanisms
2. Additional CDN support
3. Download queue management
4. Bandwidth throttling options
5. Extended file format support
6. Advanced filtering capabilities
7. Performance optimization
8. Enhanced progress reporting""" 
