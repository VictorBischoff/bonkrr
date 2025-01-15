"""Logging configuration for the bunkrr package."""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Queue
from threading import Lock, Thread, Event
from typing import Optional, Dict, Any, List

class AsyncHTMLFileHandler(logging.Handler):
    """Asynchronous HTML file handler with buffering support."""
    
    def __init__(self, filename: str, mode: str = 'a', encoding: str = 'utf-8', 
                 buffer_size: int = 1024, flush_interval: float = 1.0):
        super().__init__()
        self.filename = filename
        self.mode = mode
        self.encoding = encoding
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        
        self._buffer: Queue = Queue()
        self._lock = Lock()
        self._stop_event = Event()
        self._worker: Optional[Thread] = None
        
        # Ensure log directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Start worker thread
        self._start_worker()
        
    def _start_worker(self):
        """Start the worker thread for asynchronous logging."""
        self._worker = Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        
    def _worker_loop(self):
        """Worker loop for processing log records."""
        records: List[logging.LogRecord] = []
        
        while not self._stop_event.is_set() or not self._buffer.empty():
            try:
                # Process records in batches
                try:
                    while len(records) < self.buffer_size:
                        record = self._buffer.get_nowait()
                        records.append(record)
                except:
                    pass
                
                if records:
                    self._write_records(records)
                    records = []
                else:
                    # No records, sleep briefly
                    self._stop_event.wait(0.1)
                    
            except Exception as e:
                sys.stderr.write(f"Error in log worker: {e}\n")
                
    def _write_records(self, records: List[logging.LogRecord]):
        """Write records to file with HTML formatting."""
        with self._lock:
            try:
                with open(self.filename, self.mode, encoding=self.encoding) as f:
                    for record in records:
                        # Format record as HTML
                        msg = self.format(record)
                        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
                        level_class = record.levelname.lower()
                        
                        html = f"""
                        <div class="log-entry {level_class}">
                            <span class="timestamp">{timestamp}</span>
                            <span class="level">{record.levelname}</span>
                            <span class="message">{msg}</span>
                            {'<pre class="extra">' + str(record.extra) + '</pre>' if hasattr(record, 'extra') else ''}
                        </div>
                        """
                        
                        f.write(html)
                    f.flush()
            except Exception as e:
                sys.stderr.write(f"Error writing to log file: {e}\n")
                
    def emit(self, record: logging.LogRecord):
        """Add record to buffer queue."""
        try:
            self._buffer.put(record)
        except Exception:
            self.handleError(record)
            
    def close(self):
        """Clean up resources."""
        self._stop_event.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5.0)
        super().close()

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Set up logger with console and file handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        # Console handler
        console = logging.StreamHandler()
        console.setLevel(level)
        console_format = logging.Formatter('%(levelname)-8s %(asctime)s [%(name)s] %(message)s')
        console.setFormatter(console_format)
        logger.addHandler(console)
        
        # HTML file handler
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_handler = AsyncHTMLFileHandler(
            filename=str(log_dir / f'{name}_{timestamp}.log'),
            buffer_size=100,  # Buffer up to 100 records
            flush_interval=0.5  # Flush every 500ms
        )
        html_handler.setLevel(level)
        html_format = logging.Formatter('%(message)s')
        html_handler.setFormatter(html_format)
        logger.addHandler(html_handler)
        
    return logger

def log_exception(logger: logging.Logger, exc: Exception, context: str):
    """Log exception with context."""
    logger.error(
        "Error in %s: %s",
        context,
        str(exc),
        exc_info=True,
        extra={'error_type': type(exc).__name__}
    )

def log_html_error(
    logger: logging.Logger,
    status_code: int,
    url: str,
    html_content: str,
    error_details: Optional[Dict[str, Any]] = None
):
    """Log HTML error with details."""
    # Create error HTML file
    log_dir = Path('logs/html')
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    error_file = log_dir / f'error_{timestamp}_error.html'
    
    with open(error_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.error(
        "HTTP %d error for %s (saved to %s)",
        status_code,
        url,
        error_file,
        extra={
            'status_code': status_code,
            'url': url,
            'error_file': str(error_file),
            **(error_details or {})
        }
    ) 
