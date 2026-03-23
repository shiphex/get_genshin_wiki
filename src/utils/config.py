"""Configuration loader for the crawler."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


class Config:
    """Configuration manager for the crawler."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config.yaml file
        """
        self._config: dict = {}
        self._config_path = config_path

        # Load from yaml
        if config_path and os.path.exists(config_path):
            self._load_yaml(config_path)

        # Override with environment variables
        self._load_env()

    def _load_yaml(self, path: str) -> None:
        """Load configuration from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}

    def _load_env(self) -> None:
        """Load configuration from environment variables."""
        env_mappings = {
            "WIKI_API_URL": ("mediawiki", "api_url"),
            "WIKI_BASE_URL": ("mediawiki", "base_url"),
            "REQUEST_INTERVAL": ("mediawiki", "request_interval"),
            "REQUEST_TIMEOUT": ("mediawiki", "timeout"),
            "MAX_RETRIES": ("mediawiki", "max_retries"),
            "USER_AGENT": ("mediawiki", "user_agent"),
            "OUTPUT_DIR": ("storage", "output_dir"),
            "DB_PATH": ("storage", "db_path"),
            "LOG_LEVEL": ("logging", "level"),
            "LOG_FILE": ("logging", "file"),
        }

        for env_var, (section, key) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                if section not in self._config:
                    self._config[section] = {}
                # Try to convert to appropriate type
                if key in ("request_interval", "timeout", "max_retries"):
                    try:
                        value = int(value)
                    except ValueError:
                        pass
                self._config[section][key] = value

    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get configuration value by key path.

        Args:
            *keys: Key path (e.g., "mediawiki", "api_url")
            default: Default value if key not found

        Returns:
            Configuration value
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value

    def get_section(self, section: str) -> dict:
        """Get entire configuration section."""
        return self._config.get(section, {})

    @property
    def api_url(self) -> str:
        """Get API URL."""
        return self.get("mediawiki", "api_url", default="https://wiki.biligame.com/ys/api.php")

    @property
    def base_url(self) -> str:
        """Get base URL."""
        return self.get("mediawiki", "base_url", default="https://wiki.biligame.com/ys/")

    @property
    def request_interval(self) -> float:
        """Get request interval in seconds."""
        return float(self.get("mediawiki", "request_interval", default=5))

    @property
    def timeout(self) -> int:
        """Get request timeout in seconds."""
        return int(self.get("mediawiki", "timeout", default=30))

    @property
    def max_retries(self) -> int:
        """Get max retry count."""
        return int(self.get("mediawiki", "max_retries", default=3))

    @property
    def user_agent(self) -> str:
        """Get user agent."""
        return self.get("mediawiki", "user_agent", default="get_wiki_genshin/0.1.0")

    @property
    def output_dir(self) -> str:
        """Get output directory."""
        return self.get("storage", "output_dir", default="data")

    @property
    def db_path(self) -> str:
        """Get database path."""
        return self.get("storage", "db_path", default="data/wiki.db")

    @property
    def log_level(self) -> str:
        """Get log level."""
        return self.get("logging", "level", default="INFO")

    @property
    def log_file(self) -> str:
        """Get log file path."""
        return self.get("logging", "file", default="logs/crawler.log")

    @property
    def limit_per_request(self) -> int:
        """Get items per request."""
        return int(self.get("crawler", "limit_per_request", default=50))


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from file.

    Args:
        config_path: Path to config.yaml file

    Returns:
        Config object
    """
    if config_path is None:
        # Try default locations
        default_paths = [
            "configs/config.yaml",
            "config.yaml",
            os.path.join(os.path.dirname(__file__), "..", "..", "configs", "config.yaml"),
        ]
        for path in default_paths:
            if os.path.exists(path):
                config_path = path
                break

    return Config(config_path)
