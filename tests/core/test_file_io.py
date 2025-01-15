"""Tests for file I/O optimizations."""
import asyncio
import io
import pytest
import time
from pathlib import Path
import aiofiles
import os
import signal

from bunkrr.data_processing import (
    write_buffered,
    flush_buffer,
    WRITE_BUFFER_SIZE,
    DOWNLOAD_CHUNK_SIZE
)

@pytest.mark.asyncio
async def test_write_buffered():
    """Test that write_buffered correctly buffers and writes data."""
    test_file = Path('test_write_buffered.bin')
    buffer = io.BytesIO()
    
    try:
        # Create test data slightly larger than buffer size
        test_data = b'x' * (WRITE_BUFFER_SIZE + 1000)
        
        class MockFile:
            def __init__(self):
                self.written_data = bytearray()
                self.write_count = 0
                
            async def write(self, data):
                self.written_data.extend(data)
                self.write_count += 1
        
        mock_file = MockFile()
        
        # Write data in chunks
        chunk_size = WRITE_BUFFER_SIZE // 4
        for i in range(0, len(test_data), chunk_size):
            chunk = test_data[i:i + chunk_size]
            await write_buffered(mock_file, chunk, buffer)
            
        # Flush remaining data
        await flush_buffer(mock_file, buffer)
        
        # Verify results
        assert bytes(mock_file.written_data) == test_data
        # Should have at least one full buffer write and one partial
        assert mock_file.write_count >= 2
        
    finally:
        if test_file.exists():
            test_file.unlink()

@pytest.mark.asyncio
async def test_buffer_performance():
    """Test that buffered writes are faster than unbuffered."""
    test_file_buffered = Path('test_buffered.bin')
    test_file_unbuffered = Path('test_unbuffered.bin')
    buffer = io.BytesIO()
    
    try:
        # Create 10MB of test data
        test_data = b'x' * (10 * 1024 * 1024)
        chunk_size = 8192  # Typical chunk size
        
        # Test unbuffered writes
        start_time = time.time()
        async with aiofiles.open(test_file_unbuffered, 'wb') as f:
            for i in range(0, len(test_data), chunk_size):
                await f.write(test_data[i:i + chunk_size])
        unbuffered_time = time.time() - start_time
        
        # Test buffered writes
        start_time = time.time()
        async with aiofiles.open(test_file_buffered, 'wb') as f:
            for i in range(0, len(test_data), chunk_size):
                await write_buffered(f, test_data[i:i + chunk_size], buffer)
            await flush_buffer(f, buffer)
        buffered_time = time.time() - start_time
        
        # Buffered writes should be faster
        assert buffered_time < unbuffered_time
        
        # Verify file contents are identical
        async with aiofiles.open(test_file_buffered, 'rb') as f1, \
                  aiofiles.open(test_file_unbuffered, 'rb') as f2:
            content1 = await f1.read()
            content2 = await f2.read()
            assert content1 == content2
        
    finally:
        for file in [test_file_buffered, test_file_unbuffered]:
            if file.exists():
                file.unlink()

@pytest.mark.asyncio
async def test_chunk_size_validation():
    """Test that chunk sizes are appropriate for memory efficiency."""
    # DOWNLOAD_CHUNK_SIZE should be a power of 2 and reasonable size
    assert DOWNLOAD_CHUNK_SIZE & (DOWNLOAD_CHUNK_SIZE - 1) == 0
    assert 32 * 1024 <= DOWNLOAD_CHUNK_SIZE <= 256 * 1024
    
    # WRITE_BUFFER_SIZE should be a power of 2 and larger than chunk size
    assert WRITE_BUFFER_SIZE & (WRITE_BUFFER_SIZE - 1) == 0
    assert WRITE_BUFFER_SIZE >= DOWNLOAD_CHUNK_SIZE
    assert WRITE_BUFFER_SIZE <= 8 * 1024 * 1024  # Not too large

@pytest.mark.asyncio
async def test_buffer_flush():
    """Test that buffer is properly flushed when full or explicitly called."""
    buffer = io.BytesIO()
    written_data = bytearray()
    
    class MockFile:
        async def write(self, data):
            written_data.extend(data)
    
    mock_file = MockFile()
    
    # Write exactly one buffer size worth of data
    test_data = b'x' * WRITE_BUFFER_SIZE
    await write_buffered(mock_file, test_data, buffer)
    
    # Buffer should have been automatically flushed
    assert len(written_data) == WRITE_BUFFER_SIZE
    
    # Write partial buffer and flush explicitly
    partial_data = b'y' * 100
    await write_buffered(mock_file, partial_data, buffer)
    await flush_buffer(mock_file, buffer)
    
    # All data should be written
    assert len(written_data) == WRITE_BUFFER_SIZE + 100
    assert written_data == test_data + partial_data 

@pytest.mark.asyncio
async def test_buffer_overflow():
    """Test handling of buffer overflow conditions."""
    buffer = io.BytesIO()
    written_data = bytearray()
    write_count = 0
    
    class MockFile:
        async def write(self, data):
            nonlocal written_data, write_count
            write_count += 1
            if write_count > 5:  # Simulate buffer overflow after 5 writes
                raise IOError("Buffer overflow")
            written_data.extend(data)
    
    mock_file = MockFile()
    
    # Write data larger than what the mock can handle
    chunk_size = WRITE_BUFFER_SIZE // 2  # Smaller chunks for better control
    test_data = b'x' * (chunk_size * 10)
    
    try:
        with pytest.raises(IOError, match="Buffer overflow"):
            for i in range(0, len(test_data), chunk_size):
                chunk = test_data[i:i + chunk_size]
                await write_buffered(mock_file, chunk, buffer)
                await flush_buffer(mock_file, buffer)  # Force flush after each write
    finally:
        buffer.close()
    
    # Verify that data written before error is correct
    expected_data = test_data[:chunk_size * 5]
    assert len(written_data) == len(expected_data), f"Expected {len(expected_data)} bytes, got {len(written_data)}"
    assert written_data == expected_data

@pytest.mark.asyncio
async def test_interrupted_write():
    """Test handling of interrupted write operations."""
    test_file = Path('test_interrupted.bin')
    buffer = io.BytesIO()
    
    try:
        # Create test data
        test_data = b'x' * (WRITE_BUFFER_SIZE * 2)
        
        class InterruptedFile:
            def __init__(self):
                self.write_count = 0
                self.written_data = bytearray()
                
            async def write(self, data):
                self.write_count += 1
                if self.write_count == 2:  # Interrupt second write
                    raise asyncio.CancelledError()
                self.written_data.extend(data)
        
        mock_file = InterruptedFile()
        
        # Write data until interrupted
        with pytest.raises(asyncio.CancelledError):
            for i in range(0, len(test_data), WRITE_BUFFER_SIZE):
                chunk = test_data[i:i + WRITE_BUFFER_SIZE]
                await write_buffered(mock_file, chunk, buffer)
        
        # Verify partial write
        assert len(mock_file.written_data) == WRITE_BUFFER_SIZE
        
    finally:
        if test_file.exists():
            test_file.unlink()

@pytest.mark.asyncio
async def test_disk_full_handling():
    """Test handling of disk full conditions."""
    test_file = Path('test_disk_full.bin')
    buffer = io.BytesIO()
    
    try:
        # Create test data
        test_data = b'x' * WRITE_BUFFER_SIZE
        
        class DiskFullFile:
            async def write(self, data):
                raise OSError(28, "No space left on device")  # errno 28 is disk full
        
        mock_file = DiskFullFile()
        
        # Attempt write
        with pytest.raises(OSError) as exc_info:
            await write_buffered(mock_file, test_data, buffer)
        
        assert exc_info.value.errno == 28
        
    finally:
        if test_file.exists():
            test_file.unlink()

@pytest.mark.asyncio
async def test_concurrent_buffer_access():
    """Test concurrent access to the same buffer."""
    buffer = io.BytesIO()
    written_data = bytearray()
    
    class MockFile:
        async def write(self, data):
            await asyncio.sleep(0.01)  # Simulate I/O delay
            written_data.extend(data)
    
    mock_file = MockFile()
    
    # Create multiple write tasks
    chunks = [b'x' * 1000, b'y' * 1000, b'z' * 1000]
    tasks = [write_buffered(mock_file, chunk, buffer) for chunk in chunks]
    
    # Run tasks concurrently
    await asyncio.gather(*tasks)
    
    # Flush remaining data
    await flush_buffer(mock_file, buffer)
    
    # Verify all data was written
    assert len(written_data) == 3000
    assert all(chunk in written_data for chunk in chunks)

@pytest.mark.asyncio
async def test_partial_write():
    """Test handling of partial writes."""
    test_file = Path('test_partial.bin')
    buffer = io.BytesIO()
    
    try:
        class PartialWriteFile:
            def __init__(self):
                self.written_data = bytearray()
                
            async def write(self, data):
                # Only write half of the data each time
                half = len(data) // 2
                self.written_data.extend(data[:half])
                await asyncio.sleep(0.01)  # Simulate I/O delay
                self.written_data.extend(data[half:])
        
        mock_file = PartialWriteFile()
        
        # Write test data
        test_data = b'x' * WRITE_BUFFER_SIZE
        await write_buffered(mock_file, test_data, buffer)
        await flush_buffer(mock_file, buffer)
        
        # Verify all data was written
        assert mock_file.written_data == test_data
        
    finally:
        if test_file.exists():
            test_file.unlink()

@pytest.mark.asyncio
async def test_zero_length_write():
    """Test handling of zero-length writes."""
    buffer = io.BytesIO()
    written_data = bytearray()
    
    class MockFile:
        async def write(self, data):
            written_data.extend(data)
    
    mock_file = MockFile()
    
    # Test empty write
    await write_buffered(mock_file, b'', buffer)
    await flush_buffer(mock_file, buffer)
    
    assert len(written_data) == 0
    
    # Test normal write after empty write
    test_data = b'x' * 100
    await write_buffered(mock_file, test_data, buffer)
    await flush_buffer(mock_file, buffer)
    
    assert written_data == test_data
