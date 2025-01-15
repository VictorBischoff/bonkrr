

## Project Overview
Bunkrr is a media downloader application specifically designed for downloading content from Bunkr.site. It's written in Python and follows a well-structured, modular architecture.

### Core Components

1. **Main Application**

```21:170:bunkrr/__main__.py
class BunkrrApp:
    """Main application class."""
    
    def __init__(self):
        """Initialize the application."""
        self.ui = ConsoleUI()
        self.config = DownloadConfig()
        self._running = True
        self._shutdown_tasks: Set[asyncio.Task] = set()
        self._cleanup_hooks: List[asyncio.Lock] = []
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        
        # Create logs directory
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        logger.debug("BunkrrApp initialized")

    @handle_errors(target_error=BunkrrError, context='signal_handler')
    def _handle_interrupt(self, signum: int, frame) -> None:
        """Handle interrupt signals."""
        if not self._running:
            return
            
        self._running = False
        logger.info("Received interrupt signal %d, cleaning up...", signum)
        self.ui.print_warning("\nReceived interrupt signal, cleaning up...")
        
        # Schedule shutdown in the event loop
        if asyncio.get_event_loop().is_running():
            asyncio.create_task(self._shutdown())
    @asynccontextmanager
    async def cleanup_hook(self) -> None:
        """Context manager for cleanup operations.
        
        Usage:
            async with app.cleanup_hook():
                # Your code here
                # Will be cleaned up properly on shutdown
        """
        lock = asyncio.Lock()
        self._cleanup_hooks.append(lock)
        try:
            async with lock:
                yield
        finally:
            self._cleanup_hooks.remove(lock)

    async def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Starting graceful shutdown...")
        
        try:
            # Wait for cleanup hooks to complete
            if self._cleanup_hooks:
                logger.debug("Waiting for %d cleanup hooks...", len(self._cleanup_hooks))
                await asyncio.gather(*(hook.acquire() for hook in self._cleanup_hooks))
            
            # Cancel pending tasks
            pending = [t for t in self._shutdown_tasks if not t.done()]
            if pending:
                logger.debug("Cancelling %d pending tasks...", len(pending))
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            
            logger.info("Graceful shutdown completed")
            
        except Exception as e:
            logger.error("Error during shutdown: %s", str(e))
            raise ShutdownError("Failed to perform graceful shutdown") from e
    ...
    @handle_async_errors(target_error=BunkrrError, context='app_run')
    async def run(self) -> int:
        """Run the application.
        
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        try:
            # Import MediaProcessor here to avoid early reactor import
            from .scrapy import MediaProcessor
            
            # Print welcome message
            self.ui.print_welcome()
            
            # Get URLs from user
            urls = self.ui.get_urls()
            if not urls:
                self.ui.print_error("No valid URLs provided")
                return 1
                
            # Get download path
            download_path = self.ui.get_download_path(default=self.config.downloads_path)
            if not download_path:
                self.ui.print_error("No valid download path provided")
                return 1
                
            logger.debug("Starting URL processing with download path: %s", download_path)
            
            # Process URLs
            async with MediaProcessor(self.config) as processor:
                total_success = total_failed = 0
                
                for url in urls:
                    if not self._running:
                        logger.info("Processing interrupted by user")
                        break
                        
                    logger.debug("Processing URL: %s", url)
                    success, failed = await processor.process_urls([url], download_path)
                    total_success += success
                    total_failed += failed
                    logger.debug(
                        "URL %s processed. Success: %d, Failed: %d",
                        url, success, failed
                    )
            # Print final stats
            if total_success > 0 or total_failed > 0:
                logger.info(
                    "Download complete. Total success: %d, Total failed: %d",
                    total_success, total_failed
                )
                self.ui.print_success(
                    f"\nDownload complete: {total_success} successful, "
                    f"{total_failed} failed"
                )
            
            # Perform graceful shutdown
            await self._shutdown()
            return 0 if total_failed == 0 else 1
            
        except BunkrrError as e:
            self.ui.print_error(str(e))
            return 1
            
        except Exception as e:
            log_exception(logger, e, "running application")
            self.ui.print_error(f"An unexpected error occurred: {e}")
            return 1
```

The main application class (`BunkrrApp`) handles the core functionality, including:
- Initialization and configuration
- Signal handling for graceful shutdowns
- Asynchronous operation management
- Download coordination

2. **Error Handling System**
The project implements a comprehensive error handling system with custom exceptions and error codes:

```106:125:tests/core/test_exceptions.py
@pytest.mark.unit
class TestErrorCodes:
    """Test error code mapping."""
    
    def test_error_code_mapping(self):
        """Test error code mappings."""
        assert ERROR_CODES[ConfigError] == 'CONFIG_ERROR'
        assert ERROR_CODES[ValidationError] == 'VALIDATION_ERROR'
        assert ERROR_CODES[DownloadError] == 'DOWNLOAD_ERROR'
        assert ERROR_CODES[RateLimitError] == 'RATE_LIMIT_ERROR'
        assert ERROR_CODES[FileSystemError] == 'FILESYSTEM_ERROR'
        assert ERROR_CODES[ScrapyError] == 'SCRAPY_ERROR'
        assert ERROR_CODES[HTTPError] == 'HTTP_ERROR'
        
    def test_error_inheritance(self):
        """Test error class inheritance."""
        assert issubclass(ConfigVersionError, ConfigError)
        assert issubclass(ConfigError, BunkrrError)
        assert issubclass(ValidationError, BunkrrError)
        assert issubclass(ShutdownError, BunkrrError)
```


3. **Progress Tracking**
A sophisticated progress tracking system with console UI:

```171:254:bunkrr/ui/progress.py
    def _generate_layout(self) -> Panel:
        """Generate rich layout with progress and stats."""
        # Create stats table with improved formatting
        stats_table = Table.grid(padding=1)
        stats_table.add_row(
            Text("Files:", style="stats"),
            Text(f"{self.stats.completed_files}/{self.stats.total_files}", style="stats.value")
        )
        stats_table.add_row(
            Text("Success Rate:", style="stats"),
            Text(f"{self.stats.success_rate:.1f}%", 
                 style="summary.success" if self.stats.success_rate > 90 else "summary.error")
        )
        stats_table.add_row(
            Text("Downloaded:", style="stats"),
            Text(self.stats.formatted_downloaded_size, style="stats.value")
        )
        stats_table.add_row(
            Text("Elapsed Time:", style="stats"),
            Text(self.stats.formatted_elapsed_time, style="stats.value")
        )
        
        # Create layout with improved spacing and alignment
        layout = Table.grid(padding=1)
        layout.add_row(Panel(
            Align.center(stats_table),
            title="Download Statistics",
            border_style="panel.border",
            title_align="center"
        ))
        layout.add_row(Panel(
            self.total_progress,
            border_style="panel.border"
        ))
        layout.add_row(Panel(
            self.progress,
            title=f"Current Album: {self.current_album or 'None'}",
            border_style="panel.border",
            title_align="center"
        ))
        
        return Panel(
            layout,
            title="[summary.title]Bunkrr Downloader",
            border_style="panel.border",
            padding=(1, 2)
        )
    def _show_summary(self):
        """Show download summary with enhanced formatting."""
        summary = Table.grid(padding=1)
        summary.add_row(
            Text("Total Files:", style="stats"),
            Text(str(self.stats.total_files), style="stats.value")
        )
        summary.add_row(
            Text("Successfully Downloaded:", style="stats"),
            Text(str(self.stats.completed_files), style="summary.success")
        )
        summary.add_row(
            Text("Failed:", style="stats"),
            Text(str(self.stats.failed_files), style="summary.error")
        )
        summary.add_row(
            Text("Total Downloaded:", style="stats"),
            Text(self.stats.formatted_downloaded_size, style="summary.info")
        )
        summary.add_row(
            Text("Total Time:", style="stats"),
            Text(self.stats.formatted_elapsed_time, style="stats.value")
        )
        summary.add_row(
            Text("Success Rate:", style="stats"),
            Text(f"{self.stats.success_rate:.1f}%",
                 style="summary.success" if self.stats.success_rate > 90 else "summary.error")
        )
        
        self.console.print("\n")
        self.console.print(Panel(
            Align.center(summary),
            title="[summary.title]Download Summary",
            border_style="panel.border",
            padding=(1, 2)
        ))
```


### Key Features

1. **Media Processing**
- Supports multiple file types
- Handles album and single file downloads
- Implements rate limiting and concurrent downloads

2. **Caching System**

```84:113:bunkrr/utils/storage.py
class Cache:
    """Base class for caching implementations."""
    
    def __init__(self, config: CacheConfig):
        """Initialize cache with configuration."""
        self.config = config
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        raise NotImplementedError
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        raise NotImplementedError
    
    def delete(self, key: str) -> None:
        """Delete value from cache."""
        raise NotImplementedError
    
    def clear(self) -> None:
        """Clear all values from cache."""
        raise NotImplementedError
    
    def has(self, key: str) -> bool:
        """Check if key exists in cache."""
        raise NotImplementedError
    
    def get_size(self) -> int:
        """Get current cache size."""
        raise NotImplementedError
```


3. **Configuration Management**
- Flexible configuration system
- Version control for configs
- Environment-specific settings

### Project Structure
Based on the test directory structure:

````5:23:tests/README.md
```
tests/
├── conftest.py           # Shared test fixtures and configuration
├── core/                 # Core component tests
│   ├── test_connection.py
│   └── test_file_io.py
├── downloader/           # Download functionality tests
│   └── test_rate_limiter.py
├── scrapy/              # Scrapy integration tests
│   ├── test_processor.py
│   └── test_html_parser.py
├── ui/                  # User interface tests
│   └── test_user_input.py
├── utils/               # Utility module tests
├── integration/         # Integration tests
├── performance/         # Performance tests
│   └── test_performance.py
└── security/           # Security tests
```
````


### Development Guidelines
The project follows strict development guidelines defined in:

```2:96:.cursorrules
  "ai": {
    "preferredLibraries": [
      "requests",
      "bs4",
      "selenium",
      "scrapy",
      "jina",
      "firecrawl",
      "agentql",
      "multion",
      "lxml",
      "pandas"
    ],
    "avoidPatterns": [
      "deprecatedAPIs",
      "hardcodedCredentials",
      "unoptimizedLoops"
    ],
    "formatting": {
      "indent": "spaces",
      "indentSize": 4,
      "maxLineLength": 88,
      "quoteStyle": "double"
    },
    "codeStyle": {
      "followPEP8": true,
      "useTypeHints": true,
      "preferFStrings": true
    }
  },
  "scraping": {
    "general": {
      "useRequestsForStaticSites": true,
      "useBeautifulSoupForParsing": true,
      "useScrapyForLargeScale": true,
      "useSeleniumForDynamicContent": true,
      "respectRobotsTxt": true,
      "rateLimiting": {
        "enabled": true,
        "delay": "random",
        "minDelay": 1,
        "maxDelay": 5
      }
    },
    "textData": {
      "useJinaForStructuredData": true,
      "useFirecrawlForDeepWeb": true,
      "useScrapyForHierarchicalExtraction": true,
      "preferXPathOverCSS": false
    },
    "complexProcesses": {
      "useAgentQLForKnownWorkflows": true,
      "useScrapyForMultiStepWorkflows": true,
      "useMultionForExploratoryTasks": true,
      "automateCaptchaSolving": false
    },
    "dataHandling": {
      "validateDataBeforeProcessing": true,
      "handleMissingData": "flag",
      "storageFormats": ["csv", "json", "sqlite"],
      "useScrapyPipelines": true,
      "cloudStorageIntegration": "optional"
    },
    "errorHandling": {
      "retryLogic": {
        "enabled": true,
        "maxRetries": 3,
        "exponentialBackoff": true
      },
      "commonErrors": {
        "connectionTimeouts": true,
        "parsingErrors": true,
        "dynamicContentIssues": true,
        "scrapySpecificErrors": true
      },
      "logging": {
        "enabled": true,
        "level": "debug"
      }
    },
    "performance": {
      "optimizeParsing": true,
      "useConcurrentRequests": true,
      "useAsyncioForConcurrency": true,
      "implementCaching": true,
      "profilingTools": ["cProfile", "line_profiler"]
    }
  },
  "conventions": {
    "exploratoryAnalysis": true,
    "modularizeCode": true,
    "documentAssumptions": true,
    "useVersionControl": true,
    "ethicalScraping": true
  }
```


Key aspects include:
- Type hints and PEP 8 compliance
- Comprehensive error handling
- Rate limiting and ethical scraping practices
- Performance optimization
- Security-first development approach

### License
The project is released under the MIT License, allowing for free use, modification, and distribution.

This appears to be a well-organized, production-grade application with proper testing, error handling, and performance considerations built in from the ground up.
