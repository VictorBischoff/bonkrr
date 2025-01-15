## Project Overview
Bunkrr is a media downloader application specifically designed for downloading content from Bunkr.site. It's written in Python and follows a well-structured, modular architecture.

### Core Components

1. **Main Application**
The main application class (`BunkrrApp`) handles the core functionality, including:
- Initialization and configuration
- Signal handling for graceful shutdowns
- Asynchronous operation management
- Download coordination

2. **Error Handling System**
The project implements a comprehensive error handling system with custom exceptions and error codes:
- `BunkrrError` as the base exception
- Specialized exceptions like `ConfigError`, `ValidationError`, `DownloadError`
- Error code mapping for consistent error reporting
- Graceful error recovery mechanisms

3. **Progress Tracking**
A sophisticated progress tracking system with console UI:
- Real-time download progress updates
- Detailed statistics display
- Color-coded status indicators
- Customizable layouts

4. **Media Processing**
- Supports multiple file types
- Handles album and single file downloads
- Implements rate limiting and concurrent downloads
- Type-safe callback system for request handling

5. **Caching System**
A flexible caching system with multiple implementations:
- Protocol-based interface design
- Memory cache with LRU eviction
- File-based persistent cache
- SQLite-based cache with connection pooling
- Thread-safe operations

### Key Features

1. **Type Safety**
- Comprehensive type hints throughout the codebase
- Protocol-based interface definitions
- Generic type support for callbacks
- Runtime type checking capabilities

2. **Error Handling**
- Structured error hierarchy
- Context-aware error handling
- Detailed error reporting
- Graceful degradation

3. **Performance Optimization**
- Connection pooling
- Batch processing
- Memory-efficient data structures
- Resource cleanup mechanisms

4. **Security**
- Input validation
- Safe file handling
- Rate limiting
- Secure configuration management

### Project Structure
```
bunkrr/
├── __init__.py
├── __main__.py
├── core/
│   ├── config.py
│   ├── exceptions.py
│   └── error_handler.py
├── downloader/
│   ├── downloader.py
│   └── rate_limiter.py
├── scrapy/
│   ├── middlewares.py
│   ├── pipelines.py
│   ├── processor.py
│   └── spiders/
│       └── bunkr_spider.py
├── ui/
│   ├── progress.py
│   └── themes.py
└── utils/
    └── storage.py
```

### Development Guidelines

1. **Code Quality**
- Type hints required for all functions
- PEP 8 compliance
- Comprehensive docstrings
- Unit test coverage

2. **Error Handling**
- All exceptions must be documented
- Error messages must be descriptive
- Recovery mechanisms required
- Logging for debugging

3. **Performance**
- Resource cleanup required
- Memory usage optimization
- Connection pooling
- Batch processing where applicable

4. **Security**
- Input validation required
- Safe file operations
- Rate limiting implementation
- No hardcoded credentials

### License
The project is released under the MIT License, allowing for free use, modification, and distribution.

This is a well-organized, production-grade application with proper testing, error handling, and performance considerations built in from the ground up.
