"""Tests for HTML parser optimizations."""
import pytest
from bs4 import BeautifulSoup, SoupStrainer
from bunkrr.data_processing import create_soup, ALBUM_STRAINER, MEDIA_STRAINER

# Sample HTML content for testing
ALBUM_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="Test Album">
</head>
<body>
    <h1 class="truncate">Test Album Header</h1>
    <span class="font-semibold">10 items</span>
    <div class="theItem">
        <a aria-label="download" href="/f/abc123">
            <p style="display:none;">test_file.mp4</p>
            <p class="theSize">10 MB</p>
            <span class="theDate">2024-01-15</span>
            <img class="grid-images_box-img" src="thumbnail.jpg">
        </a>
    </div>
    <div class="irrelevant">Should not be parsed</div>
</body>
</html>
"""

MEDIA_HTML = """
<!DOCTYPE html>
<html>
<body>
    <video>
        <source src="video.mp4" type="video/mp4">
    </video>
    <div class="irrelevant">Should not be parsed</div>
</body>
</html>
"""

# Edge case HTML content
MALFORMED_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="Test Album">
</head>
<body>
    <h1 class="truncate">Unclosed h1
    <div class="theItem">
        <a aria-label="download" href="/f/abc123">
            <p style="display:none;">test_file.mp4
            <p class="theSize">10 MB
            <span class="theDate">2024-01-15
            <img class="grid-images_box-img" src="thumbnail.jpg">
        </a>
    <div class="irrelevant">Unclosed div
</body>
"""

EMPTY_HTML = """
<!DOCTYPE html>
<html>
<head></head>
<body></body>
</html>
"""

NESTED_HTML = """
<!DOCTYPE html>
<html>
<body>
    <div class="theItem">
        <div class="theItem">  <!-- Nested item -->
            <a aria-label="download" href="/f/abc123">
                <p style="display:none;">nested.mp4</p>
            </a>
        </div>
        <a aria-label="download" href="/f/def456">
            <p style="display:none;">outer.mp4</p>
        </a>
    </div>
</body>
</html>
"""

MIXED_CONTENT_HTML = """
<!DOCTYPE html>
<html>
<body>
    <video>
        <source src="video.mp4" type="video/mp4">
    </video>
    <div class="theItem">
        <a aria-label="download" href="/f/abc123">
            <p style="display:none;">mixed.mp4</p>
        </a>
    </div>
</body>
</html>
"""

@pytest.mark.asyncio
async def test_create_soup_caching():
    """Test that create_soup properly caches results."""
    # First call should create new soup
    soup1 = create_soup(ALBUM_HTML, 'lxml')
    # Second call with same content should return cached result
    soup2 = create_soup(ALBUM_HTML, 'lxml')
    
    # Verify both soups are identical (same object due to caching)
    assert soup1 is soup2
    
    # Different content should create new soup
    soup3 = create_soup(MEDIA_HTML, 'lxml')
    assert soup1 is not soup3

def test_album_strainer_optimization():
    """Test that ALBUM_STRAINER correctly limits parsing scope."""
    # Parse with strainer
    soup_with_strainer = create_soup(ALBUM_HTML, 'lxml', ALBUM_STRAINER)
    
    # Parse without strainer
    full_soup = BeautifulSoup(ALBUM_HTML, 'lxml')
    
    # Verify strainer included required elements
    assert soup_with_strainer.find('meta', property='og:title') is not None
    assert soup_with_strainer.find('h1', class_='truncate') is not None
    assert soup_with_strainer.find('div', class_='theItem') is not None
    
    # Verify strainer excluded irrelevant elements
    assert soup_with_strainer.find('div', class_='irrelevant') is None
    assert full_soup.find('div', class_='irrelevant') is not None

def test_media_strainer_optimization():
    """Test that MEDIA_STRAINER correctly limits parsing scope."""
    # Parse with strainer
    soup_with_strainer = create_soup(MEDIA_HTML, 'lxml', MEDIA_STRAINER)
    
    # Parse without strainer
    full_soup = BeautifulSoup(MEDIA_HTML, 'lxml')
    
    # Verify strainer included required elements
    assert soup_with_strainer.find('video') is not None
    assert soup_with_strainer.find('source') is not None
    
    # Verify strainer excluded irrelevant elements
    assert soup_with_strainer.find('div', class_='irrelevant') is None
    assert full_soup.find('div', class_='irrelevant') is not None

def test_parser_performance():
    """Test performance improvement with lxml parser and strainers."""
    import time
    
    # Test parsing time with lxml and strainer
    start_time = time.time()
    for _ in range(100):
        create_soup(ALBUM_HTML, 'lxml', ALBUM_STRAINER)
    lxml_time = time.time() - start_time
    
    # Test parsing time with default parser and no strainer
    start_time = time.time()
    for _ in range(100):
        BeautifulSoup(ALBUM_HTML, 'html.parser')
    default_time = time.time() - start_time
    
    # lxml with strainer should be significantly faster
    assert lxml_time < default_time

def test_parse_album_content():
    """Test that album content is correctly parsed with optimizations."""
    soup = create_soup(ALBUM_HTML, 'lxml', ALBUM_STRAINER)
    
    # Test meta title extraction
    meta_title = soup.find('meta', property='og:title', attrs={'content': True})
    assert meta_title['content'] == 'Test Album'
    
    # Test h1 title extraction
    h1_title = soup.find('h1', class_='truncate')
    assert h1_title.get_text(strip=True) == 'Test Album Header'
    
    # Test media item extraction
    media_item = soup.find('div', class_='theItem')
    assert media_item is not None
    
    # Test file info extraction
    filename = media_item.find('p', style='display:none;').get_text(strip=True)
    assert filename == 'test_file.mp4'
    
    size = media_item.find('p', class_='theSize').get_text(strip=True)
    assert size == '10 MB'
    
    date = media_item.find('span', class_='theDate').get_text(strip=True)
    assert date == '2024-01-15'
    
    thumbnail = media_item.find('img', class_='grid-images_box-img')['src']
    assert thumbnail == 'thumbnail.jpg'

def test_parse_media_content():
    """Test that media content is correctly parsed with optimizations."""
    soup = create_soup(MEDIA_HTML, 'lxml', MEDIA_STRAINER)
    
    # Test video source extraction
    video = soup.find('video')
    assert video is not None
    
    source = video.find('source', attrs={'src': True})
    assert source['src'] == 'video.mp4' 

@pytest.mark.asyncio
async def test_malformed_html_handling():
    """Test parsing of malformed HTML."""
    soup = create_soup(MALFORMED_HTML, 'lxml', ALBUM_STRAINER)
    
    # Should still find valid elements
    assert soup.find('meta', property='og:title') is not None
    assert soup.find('h1', class_='truncate') is not None
    assert soup.find('div', class_='theItem') is not None
    
    # Should handle unclosed tags
    h1 = soup.find('h1', class_='truncate')
    assert h1 is not None
    # Extract text and clean it
    h1_text = ' '.join(h1.stripped_strings).split('test_file')[0].strip()
    assert h1_text == 'Unclosed h1', f"Got unexpected text: {h1_text}"

@pytest.mark.asyncio
async def test_empty_html_handling():
    """Test parsing of empty HTML."""
    soup = create_soup(EMPTY_HTML, 'lxml', ALBUM_STRAINER)
    
    # Should handle empty content gracefully
    assert soup.find('meta', property='og:title') is None
    assert soup.find('div', class_='theItem') is None
    assert soup.find('video') is None

@pytest.mark.asyncio
async def test_nested_content_handling():
    """Test parsing of nested content."""
    soup = create_soup(NESTED_HTML, 'lxml', ALBUM_STRAINER)
    
    # Should find both outer and nested items
    items = soup.find_all('div', class_='theItem')
    assert len(items) == 2
    
    # Should find both download links
    links = soup.find_all('a', attrs={'aria-label': 'download'})
    assert len(links) == 2
    
    # Verify filenames
    filenames = [p.get_text(strip=True) for p in soup.find_all('p', style='display:none;')]
    assert 'nested.mp4' in filenames
    assert 'outer.mp4' in filenames

@pytest.mark.asyncio
async def test_mixed_content_handling():
    """Test parsing of mixed content types."""
    # Test with album strainer
    album_soup = create_soup(MIXED_CONTENT_HTML, 'lxml', ALBUM_STRAINER)
    assert album_soup.find('div', class_='theItem') is not None
    assert album_soup.find('video') is None  # Should not include video tag
    
    # Test with media strainer
    media_soup = create_soup(MIXED_CONTENT_HTML, 'lxml', MEDIA_STRAINER)
    assert media_soup.find('video') is not None
    assert media_soup.find('div', class_='theItem') is None  # Should not include item div

@pytest.mark.asyncio
async def test_large_html_performance():
    """Test parsing performance with large HTML."""
    # Create large HTML with many items
    large_html = """<!DOCTYPE html><html><body>"""
    for i in range(1000):  # 1000 items
        large_html += f"""
        <div class="theItem">
            <a aria-label="download" href="/f/item{i}">
                <p style="display:none;">file{i}.mp4</p>
                <p class="theSize">10 MB</p>
                <span class="theDate">2024-01-15</span>
                <img class="grid-images_box-img" src="thumb{i}.jpg">
            </a>
        </div>
        """
    large_html += """</body></html>"""
    
    import time
    
    # Test with strainer multiple times to get consistent results
    strainer_times = []
    full_times = []
    
    for _ in range(3):  # Run multiple times
        # Test with strainer
        start_time = time.time()
        soup_with_strainer = create_soup(large_html, 'lxml', ALBUM_STRAINER)
        strainer_times.append(time.time() - start_time)
        
        # Test without strainer
        start_time = time.time()
        soup_without_strainer = BeautifulSoup(large_html, 'lxml')
        full_times.append(time.time() - start_time)
    
    # Use median times for comparison
    strainer_time = sorted(strainer_times)[1]  # Median of 3
    full_time = sorted(full_times)[1]  # Median of 3
    
    # Strainer should be significantly faster
    assert strainer_time < full_time, f"Strainer time ({strainer_time:.3f}s) not faster than full parse ({full_time:.3f}s)"
    
    # Both should find all items
    assert len(soup_with_strainer.find_all('div', class_='theItem')) == 1000
    assert len(soup_without_strainer.find_all('div', class_='theItem')) == 1000

@pytest.mark.asyncio
async def test_cache_invalidation():
    """Test that cache is properly invalidated for different inputs."""
    # First call should create new soup
    soup1 = create_soup(ALBUM_HTML, 'lxml')
    
    # Modify HTML slightly
    modified_html = ALBUM_HTML.replace('Test Album', 'Modified Album')
    soup2 = create_soup(modified_html, 'lxml')
    
    # Should be different objects
    assert soup1 is not soup2
    
    # Verify content is different
    title1 = soup1.find('meta', property='og:title')['content']
    title2 = soup2.find('meta', property='og:title')['content']
    assert title1 != title2

@pytest.mark.asyncio
async def test_parser_error_handling():
    """Test handling of parser errors."""
    # Test with severely malformed HTML
    broken_html = "<not>valid</html>"
    
    # Should still create a soup object
    soup = create_soup(broken_html, 'lxml', ALBUM_STRAINER)
    assert soup is not None
    
    # Test with mixed encodings
    mixed_encoding = ALBUM_HTML.encode('utf-8').decode('latin1')
    soup = create_soup(mixed_encoding, 'lxml', ALBUM_STRAINER)
    assert soup is not None
    
    # Test with null bytes
    null_html = ALBUM_HTML.replace('Test Album', 'Test\x00Album')
    soup = create_soup(null_html, 'lxml', ALBUM_STRAINER)
    assert soup is not None 
