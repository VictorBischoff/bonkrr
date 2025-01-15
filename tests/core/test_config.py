"""Tests for configuration management."""
import pytest
from bunkrr.core.config import ConfigVersion, ScrapyConfig, DownloadConfig
from bunkrr.core.exceptions import ConfigError, ConfigVersionError

@pytest.mark.unit
class TestConfigVersion:
    """Test configuration version management."""
    
    def test_version_comparison(self):
        """Test version comparison functionality."""
        assert ConfigVersion.V1_0.value == "1.0"
        assert ConfigVersion.V1_1.value == "1.1"
        assert ConfigVersion.latest() == ConfigVersion.V1_1
        
    def test_version_from_string(self):
        """Test version creation from string."""
        assert ConfigVersion("1.0") == ConfigVersion.V1_0
        assert ConfigVersion("1.1") == ConfigVersion.V1_1
        with pytest.raises(ValueError):
            ConfigVersion("invalid")

@pytest.mark.unit
class TestScrapyConfig:
    """Test Scrapy configuration settings."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ScrapyConfig()
        assert config.CONCURRENT_REQUESTS == 32
        assert config.CONCURRENT_REQUESTS_PER_DOMAIN == 16
        assert config.DOWNLOAD_TIMEOUT == 30
        assert not config.ROBOTSTXT_OBEY
        
    def test_to_dict_conversion(self):
        """Test conversion to dictionary format."""
        config = ScrapyConfig()
        settings = config.to_dict()
        assert isinstance(settings, dict)
        assert settings['CONCURRENT_REQUESTS'] == 32
        assert settings['DOWNLOAD_TIMEOUT'] == 30
        assert not settings['ROBOTSTXT_OBEY']
        
    def test_migration_same_version(self):
        """Test migration with same version."""
        old_config = {'CONCURRENT_REQUESTS': 64}
        config = ScrapyConfig.migrate_from(old_config, "1.1")
        assert config.CONCURRENT_REQUESTS == 64
        
    def test_migration_invalid_version(self):
        """Test migration with invalid version."""
        old_config = {'CONCURRENT_REQUESTS': 64}
        with pytest.raises(ConfigVersionError):
            ScrapyConfig.migrate_from(old_config, "0.9")

@pytest.mark.unit
class TestDownloadConfig:
    """Test download configuration settings."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = DownloadConfig()
        assert config.max_concurrent_downloads == 6
        assert config.chunk_size == 65536  # 64KB
        assert config.buffer_size == 1048576  # 1MB
        assert config.connect_timeout == 30
        assert config.read_timeout == 300
        
    def test_validation(self):
        """Test configuration validation."""
        config = DownloadConfig()
        
        # Valid configuration
        config.validate()
        
        # Invalid max_concurrent_downloads
        config.max_concurrent_downloads = 0
        with pytest.raises(ConfigError, match="max_concurrent_downloads must be at least 1"):
            config.validate()
            
        # Invalid chunk_size
        config.max_concurrent_downloads = 6
        config.chunk_size = 512  # Less than 1KB
        with pytest.raises(ConfigError, match="chunk_size must be at least 1KB"):
            config.validate()
            
        # Invalid buffer size
        config.chunk_size = 65536
        config.buffer_size = 32768  # Less than chunk_size
        with pytest.raises(ConfigError, match="buffer_size must be at least as large as chunk_size"):
            config.validate()
            
    def test_migration_same_version(self):
        """Test migration with same version."""
        old_config = {'max_concurrent_downloads': 8}
        config = DownloadConfig.migrate_from(old_config, "1.1")
        assert config.max_concurrent_downloads == 8
        
    def test_migration_invalid_version(self):
        """Test migration with invalid version."""
        old_config = {'max_concurrent_downloads': 8}
        with pytest.raises(ConfigVersionError):
            DownloadConfig.migrate_from(old_config, "0.9")
            
    def test_scrapy_integration(self):
        """Test Scrapy configuration integration."""
        config = DownloadConfig()
        assert isinstance(config.scrapy, ScrapyConfig)
        assert config.scrapy.CONCURRENT_REQUESTS == 32 
