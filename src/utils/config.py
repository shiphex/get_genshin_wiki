"""配置加载模块"""
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_config(config_path: str = "configs/config.yaml") -> dict[str, Any]:
    """加载 YAML 配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典
    """
    path = Path(config_path)
    if not path.exists():
        # 尝试相对于项目根目录的路径
        path = Path(__file__).parent.parent.parent / config_path

    if not path.exists():
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return get_default_config()

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def get_default_config() -> dict[str, Any]:
    """获取默认配置"""
    return {
        "mediawiki": {
            "api_url": "https://wiki.biligame.com/ys/api.php",
            "base_url": "https://wiki.biligame.com/ys/",
            "request_interval": 3,
            "timeout": 30,
            "max_retries": 3,
            "user_agent": "get_wiki_genshin/0.1.0 (MediaWiki Crawler)",
        },
        "storage": {
            "output_dir": "storage",
            "books_dir": "storage/books",
            "arms_dir": "storage/arms",
            "artifacts_dir": "storage/artifacts",
            "links_dir": "storage/links",
            "book_dir": "storage/book",
            "arm_dir": "storage/arm",
            "artifact_dir": "storage/artifacts",
        },
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    }
