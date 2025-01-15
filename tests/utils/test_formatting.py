"""Test formatting utilities."""
import pytest
from datetime import datetime, timedelta
from rich.text import Text

from bunkrr.utils.formatting import (
    format_size,
    format_time,
    format_rate,
    format_progress,
    create_progress_bar,
    create_stats_table,
    truncate_text,
    wrap_text,
    strip_ansi,
    highlight_matches,
    format_duration,
    format_table
)

def test_format_size():
    """Test size formatting."""
    test_cases = [
        (0, "0 B"),
        (1024, "1.00 KB"),
        (1024 * 1024, "1.00 MB"),
        (1024 * 1024 * 1024, "1.00 GB"),
        (1024 * 1024 * 1024 * 1024, "1.00 TB"),
        (500, "500.00 B"),
        (1500, "1.46 KB"),
        (1024 * 1024 * 2.5, "2.50 MB")
    ]
    
    for size, expected in test_cases:
        assert format_size(size) == expected

def test_format_time():
    """Test time formatting."""
    test_cases = [
        (0, "0s"),
        (30, "30s"),
        (60, "1m"),
        (90, "1m 30s"),
        (3600, "1h"),
        (3661, "1h 1m 1s"),
        (86400, "1d"),
        (90061, "1d 1h 1m 1s"),
        (-1, "0s")  # Negative time
    ]
    
    for seconds, expected in test_cases:
        assert format_time(seconds) == expected

def test_format_rate():
    """Test rate formatting."""
    test_cases = [
        (0, "0/s"),
        (1024, "1.00 KB/s"),
        (1024 * 1024, "1.00 MB/s"),
        (1024 * 1024 * 1024, "1.00 GB/s"),
        (500, "500.00 B/s")
    ]
    
    for rate, expected in test_cases:
        assert format_rate(rate) == expected

def test_format_progress():
    """Test progress bar formatting."""
    # Test empty progress
    assert "[" + " " * 40 + "] 0%" == format_progress(0, 100)
    
    # Test full progress
    assert "[" + "=" * 40 + "] 100%" == format_progress(100, 100)
    
    # Test partial progress
    result = format_progress(50, 100)
    assert len(result) == 45  # [==...==] 50%
    assert result.count("=") == 20  # Half filled
    assert "50%" in result
    
    # Test zero total
    assert "[" + " " * 40 + "] 0%" == format_progress(0, 0)

def test_create_progress_bar():
    """Test progress bar creation."""
    progress = create_progress_bar("Test")
    assert progress is not None
    assert len(progress.columns) > 0
    
    # Add task and update
    task_id = progress.add_task("Test Task", total=100)
    progress.update(task_id, completed=50)
    assert progress.tasks[task_id].completed == 50

def test_create_stats_table():
    """Test statistics table creation."""
    stats = {
        'total': 100,
        'completed': 75,
        'failed': 25,
        'skipped': 0,
        'bytes_downloaded': 1024 * 1024,
        'elapsed_time': 3600,
        'success_rate': 75.0,
        'average_speed': 1024
    }
    
    table = create_stats_table(stats)
    assert table is not None
    assert len(table.rows) > 0

def test_truncate_text():
    """Test text truncation."""
    test_cases = [
        ("short text", 20, "short text"),
        ("long text to truncate", 10, "long te..."),
        ("test", 3, "..."),
        ("", 5, ""),
        ("test", 4, "test")
    ]
    
    for text, length, expected in test_cases:
        assert truncate_text(text, length) == expected

def test_wrap_text():
    """Test text wrapping."""
    text = "This is a long text that needs to be wrapped at specific width"
    
    # Test basic wrapping
    wrapped = wrap_text(text, width=20)
    assert all(len(line) <= 20 for line in wrapped)
    
    # Test with indent
    indented = wrap_text(text, width=20, indent="  ")
    assert all(line.startswith("  ") for line in indented)

def test_strip_ansi():
    """Test ANSI escape sequence stripping."""
    test_cases = [
        ("\033[31mred text\033[0m", "red text"),
        ("\033[1;32;40mgreen on black\033[0m", "green on black"),
        ("normal text", "normal text"),
        ("\033[0m\033[1m\033[31m", "")
    ]
    
    for text, expected in test_cases:
        assert strip_ansi(text) == expected

def test_highlight_matches():
    """Test pattern highlighting."""
    text = "This is a test string with TEST and test"
    pattern = r"test"
    
    result = highlight_matches(text, pattern, style="bold red")
    assert isinstance(result, Text)
    assert len(result.style_spans) > 0
    
    # Test case-sensitive
    result = highlight_matches(text, r"TEST", style="bold red")
    assert len(result.style_spans) == 1

def test_format_duration():
    """Test duration formatting."""
    now = datetime.now()
    test_cases = [
        (timedelta(seconds=30), "30s"),
        (timedelta(minutes=5), "5m"),
        (timedelta(hours=2), "2h"),
        (timedelta(days=1), "1d"),
        (timedelta(days=1, hours=2, minutes=3, seconds=4), "1d 2h 3m 4s")
    ]
    
    for delta, expected in test_cases:
        start = now - delta
        assert format_duration(start, now) == expected

def test_format_table():
    """Test table formatting."""
    headers = ["Name", "Value", "Status"]
    rows = [
        ["test1", "100", "OK"],
        ["test2", "200", "Error"]
    ]
    
    # Test basic table
    result = format_table(headers, rows)
    assert isinstance(result, str)
    assert all(header in result for header in headers)
    assert all(all(cell in result for cell in row) for row in rows)
    
    # Test empty table
    empty_result = format_table(headers, [])
    assert empty_result == ""
    
    # Test alignments
    aligned_result = format_table(
        headers,
        rows,
        alignments=["<", ">", "^"]
    )
    assert isinstance(aligned_result, str) 
