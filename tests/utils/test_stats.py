"""Test statistics utilities."""
import time
import asyncio
import pytest
from datetime import datetime, timedelta

from bunkrr.utils.stats import (
    DownloadStats,
    RateTracker,
    ProgressTracker
)

def test_download_stats():
    """Test download statistics tracking."""
    stats = DownloadStats()
    
    # Test initial state
    assert stats.total == 0
    assert stats.completed == 0
    assert stats.failed == 0
    assert stats.skipped == 0
    assert stats.bytes_downloaded == 0
    assert stats.start_time is None
    assert stats.end_time is None
    assert stats.errors == {}
    
    # Test start/stop
    stats.start()
    assert stats.start_time is not None
    assert stats.is_running
    
    time.sleep(0.1)  # Small delay
    stats.stop()
    assert stats.end_time is not None
    assert not stats.is_running
    
    # Test elapsed time
    assert stats.elapsed_time > 0
    
    # Test success rate
    stats.total = 100
    stats.completed = 75
    assert stats.success_rate == 75.0
    
    # Test average speed
    stats.bytes_downloaded = 1024 * 1024  # 1MB
    assert stats.average_speed > 0
    
    # Test error tracking
    stats.add_error("test_error")
    stats.add_error("test_error")
    assert stats.errors["test_error"] == 2
    
    # Test dictionary conversion
    data = stats.to_dict()
    assert isinstance(data, dict)
    assert data["total"] == 100
    assert data["completed"] == 75
    assert data["success_rate"] == 75.0
    assert data["errors"] == {"test_error": 2}

def test_rate_tracker():
    """Test rate tracking."""
    tracker = RateTracker(window_size=1)  # 1 second window
    
    # Test initial state
    assert tracker.get_rate() == 0.0
    
    # Test event tracking
    tracker.add_event(1)
    assert tracker.get_rate() > 0
    
    # Test wait time tracking
    tracker.add_event(1, wait_time=0.1)
    stats = tracker.get_wait_time_stats()
    assert stats["avg_wait"] == 0.1
    assert stats["max_wait"] == 0.1
    assert stats["rate_limit_hits"] == 1
    
    # Test window cleanup
    time.sleep(1.1)  # Wait for window to expire
    assert tracker.get_rate() == 0.0
    
    # Test reset
    tracker.add_event(1)
    tracker.reset()
    assert tracker.get_rate() == 0.0
    assert tracker.get_wait_time_stats()["rate_limit_hits"] == 0

def test_progress_tracker():
    """Test progress tracking."""
    tracker = ProgressTracker()
    
    # Test initial state
    assert tracker.stats.total == 0
    assert tracker.stats.completed == 0
    assert tracker.stats.failed == 0
    
    # Test start/stop
    tracker.start()
    assert tracker.stats.is_running
    
    # Test updates
    tracker.update(completed=1, bytes_downloaded=1024)
    assert tracker.stats.completed == 1
    assert tracker.stats.bytes_downloaded == 1024
    
    tracker.update(failed=1, error="test_error")
    assert tracker.stats.failed == 1
    assert "test_error" in tracker.stats.errors
    
    tracker.update(skipped=1)
    assert tracker.stats.skipped == 1
    
    # Test rate tracking
    assert tracker.rate_tracker.get_rate() > 0
    
    # Test stop
    tracker.stop()
    assert not tracker.stats.is_running
    
    # Test stats conversion
    stats = tracker.stats.to_dict()
    assert isinstance(stats, dict)
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["skipped"] == 1
    assert stats["bytes_downloaded"] == 1024
    assert stats["errors"] == {"test_error": 1}

@pytest.mark.asyncio
async def test_progress_tracker_async():
    """Test progress tracker in async context."""
    tracker = ProgressTracker()
    tracker.start()
    
    # Simulate async updates
    for _ in range(5):
        tracker.update(completed=1, bytes_downloaded=1024)
        await asyncio.sleep(0.1)
    
    tracker.stop()
    
    assert tracker.stats.completed == 5
    assert tracker.stats.bytes_downloaded == 5 * 1024
    assert tracker.rate_tracker.get_rate() > 0 
