#!/usr/bin/env python3
"""武器爬取脚本"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawler.client import MediaWikiClient
from src.parser.arms_parser import ArmsParser
from src.storage.arms_writer import ArmStorage
from src.utils.config import load_config
from src.utils.logger import setup_logging

logger = logging.getLogger(__name__)


def crawl_arm_list(client: MediaWikiClient, parser: ArmsParser, storage: ArmStorage) -> list[dict]:
    """爬取武器列表页面

    Returns:
        武器链接列表
    """
    logger.info("获取武器图鉴页面...")
    html = client.get_page_html("武器图鉴")
    links = parser.extract_arm_links(html)
    logger.info(f"找到 {len(links)} 件武器")
    return links


def crawl_single_arm(client: MediaWikiClient, parser: ArmsParser, storage: ArmStorage, title: str) -> bool:
    """爬取单件武器

    Returns:
        是否成功
    """
    try:
        logger.info(f"爬取武器: {title}")
        html = client.get_page_html(title)
        url = f"{client.base_url}{title}"

        arm = parser.parse_arm_page(html, title, url)
        arm.fetched_at = datetime.now().isoformat()

        storage.save_arm(arm)
        return True

    except Exception as e:
        logger.error(f"爬取武器失败 {title}: {e}")
        storage.save_failed_arm(title, str(e))
        return False


def main():
    """主函数"""
    setup_logging()
    logger.info("=" * 50)
    logger.info("开始武器爬取任务")
    logger.info("=" * 50)

    # 加载配置
    config = load_config()
    mw_config = config["mediawiki"]
    storage_config = config.get("storage", {})

    # 初始化组件
    client = MediaWikiClient(
        api_url=mw_config["api_url"],
        base_url=mw_config["base_url"],
        request_interval=mw_config.get("request_interval", 3),
        timeout=mw_config.get("timeout", 30),
        max_retries=mw_config.get("max_retries", 3),
        user_agent=mw_config.get("user_agent", "get_wiki_genshin/0.1.0"),
    )

    parser = ArmsParser(base_url=mw_config["base_url"])
    storage = ArmStorage(base_dir=storage_config.get("arm_dir", "storage/arm"))

    # 获取已保存和已失败的武器
    saved_arms = storage.load_saved_arms()
    failed_arms = storage.load_failed_arms()
    logger.info(f"已保存 {len(saved_arms)} 件，已失败 {len(failed_arms)} 件")

    # 爬取武器列表
    arm_links = crawl_arm_list(client, parser, storage)

    # 过滤已保存和已失败的
    arms_to_crawl = [
        link for link in arm_links
        if link["title"] not in saved_arms
        and link["title"] not in failed_arms
    ]
    logger.info(f"待爬取 {len(arms_to_crawl)} 件")

    # 爬取每件武器
    success_count = 0
    for link in arms_to_crawl:
        if crawl_single_arm(client, parser, storage, link["title"]):
            success_count += 1

    logger.info("=" * 50)
    logger.info(f"爬取完成！成功 {success_count}/{len(arms_to_crawl)} 件")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
