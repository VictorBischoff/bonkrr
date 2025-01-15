# Bunkrr Test Suite

## Directory Structure

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

## Test Categories

- **Core Tests**: Base functionality and system components
- **Downloader Tests**: Download management and rate limiting
- **Scrapy Tests**: Media processing and scraping functionality
- **UI Tests**: User interface and interaction
- **Utils Tests**: Utility functions and helpers
- **Integration Tests**: Cross-component functionality
- **Performance Tests**: Speed and resource usage
- **Security Tests**: Security measures and validation

## Running Tests

Run all tests:
```bash
pytest
```

Run specific test category:
```bash
pytest tests/core/          # Run core tests
pytest -m unit             # Run unit tests
pytest -m integration      # Run integration tests
pytest -m performance      # Run performance tests
pytest -m security         # Run security tests
pytest -m async            # Run async tests
```

## Test Conventions

1. File Naming:
   - Test files: `test_*.py`
   - Test classes: `Test*`
   - Test functions: `test_*`

2. Markers:
   - @pytest.mark.unit
   - @pytest.mark.integration
   - @pytest.mark.performance
   - @pytest.mark.security
   - @pytest.mark.async

3. Fixtures:
   - Shared fixtures in conftest.py
   - Component-specific fixtures in respective directories

4. Documentation:
   - Each test module should have a docstring
   - Each test class/function should have a clear purpose
   - Complex test scenarios should be documented 
