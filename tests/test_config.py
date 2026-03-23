"""Tests for config loader."""

import os
import pytest
from src.utils.config import Config, load_config


class TestConfig:
    """Test cases for Config."""

    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        assert config.api_url == "https://wiki.biligame.com/ys/api.php"
        assert config.base_url == "https://wiki.biligame.com/ys/"
        assert config.request_interval == 5.0
        assert config.timeout == 30
        assert config.max_retries == 3

    def test_config_get(self):
        """Test config get method."""
        config = Config()
        assert config.get("mediawiki", "api_url") == "https://wiki.biligame.com/ys/api.php"
        assert config.get("mediawiki", "nonexistent", default="default") == "default"

    def test_config_from_env(self):
        """Test loading from environment variables."""
        os.environ["REQUEST_INTERVAL"] = "10"
        config = Config()
        assert config.request_interval == 10.0
        del os.environ["REQUEST_INTERVAL"]

    def test_output_dir(self):
        """Test output directory config."""
        config = Config()
        assert config.output_dir == "data"
        assert config.db_path == "data/wiki.db"


class TestLoadConfig:
    """Test load_config function."""

    def test_load_default(self):
        """Test loading default config."""
        config = load_config()
        assert config is not None
        assert config.api_url is not None
