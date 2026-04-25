#!/usr/bin/env python3
"""圣遗物爬取脚本"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.content.runtime import run_crawl
from src.utils.config import load_config
from src.utils.logger import setup_logging

logger = logging.getLogger(__name__)


def main():
    """主函数"""
    setup_logging()
    logger.info("=" * 50)
    logger.info("开始圣遗物爬取任务")
    logger.info("=" * 50)
    result = run_crawl("artifacts", load_config())
    logger.info("爬取完成: saved=%s failed=%s manifest=%s", result.manifest["saved_count"], result.manifest["failed_count"], result.manifest_path)


if __name__ == "__main__":
    main()
