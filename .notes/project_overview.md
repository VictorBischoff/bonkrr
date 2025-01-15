# Bunkrr Project Overview

## Project Description
Bunkrr is a high-performance media downloader application designed to efficiently download media files from Bunkr.site. The application features a modern terminal user interface, robust error handling, and optimized concurrent downloads.

## Core Features
- Asynchronous media downloads with rate limiting
- Smart retry logic with exponential backoff
- Real-time progress tracking with rich terminal UI
- Concurrent download management
- Automatic file organization
- Robust error handling and logging

## Technical Architecture

### Core Components
1. **Downloader (`downloader.py`)**
   - Main orchestrator for download processes
   - Handles user input and download coordination
   - Manages download sessions and retries

2. **Media Processor (`data_processing.py`)**
   - Handles media file processing and downloads
   - Implements rate limiting and concurrent downloads
   - Manages file system operations
   - Provides optimized CDN selection

3. **User Interface (`ui.py`)**
   - Rich terminal interface with progress bars
   - Real-time statistics display
   - Download status tracking
   - Error and warning visualization

4. **Configuration (`config.py`)**
   - Centralized configuration management
   - Download settings and limits
   - Rate limiting parameters
   - File validation rules

5. **Input Handler (`user_input.py`)**
   - URL validation and processing
   - User input management
   - File path handling

6. **Logger (`logger.py`)**
   - Structured logging system
   - Error tracking and reporting
   - Debug information collection

### Performance Features
- Concurrent downloads (max 6 simultaneous)
- Rate limiting (5 requests per 60s window)
- Connection pooling and reuse
- DNS result caching
- Optimized CDN selection
- Chunk-based downloads

### Error Handling
- Automatic retries with exponential backoff
- Rate limit detection and handling
- Network error recovery
- File system error management
- Detailed error logging

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

### Testing
- Unit tests for core functionality
- Integration tests for download flows
- Error scenario testing
- Performance benchmarking

## Future Improvements
1. Enhanced error recovery mechanisms
2. Additional CDN support
3. Download queue management
4. Bandwidth throttling options
5. Extended file format support
6. Advanced filtering capabilities 
