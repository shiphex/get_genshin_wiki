#!/usr/bin/env python3
"""圣遗物爬取脚本"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawler.client import MediaWikiClient
from src.parser.artifacts_parser import ArtifactsParser
from src.storage.artifacts_writer import ArtifactStorage
from src.utils.config import load_config
from src.utils.logger import setup_logging

logger = logging.getLogger(__name__)


def crawl_artifact_list(client: MediaWikiClient, parser: ArtifactsParser, storage: ArtifactStorage) -> list[dict]:
    """爬取圣遗物列表页面

    Returns:
        圣遗物链接列表
    """
    logger.info("获取圣遗物图鉴页面...")
    html = client.get_page_html("圣遗物图鉴")
    links = parser.extract_artifact_links(html)
    logger.info(f"找到 {len(links)} 套圣遗物")
    return links


def crawl_single_artifact(client: MediaWikiClient, parser: ArtifactsParser, storage: ArtifactStorage, title: str) -> bool:
    """爬取单套圣遗物

    Returns:
        是否成功
    """
    try:
        logger.info(f"爬取圣遗物: {title}")
        html = client.get_page_html(title)
        url = f"{client.base_url}{title}"

        artifact = parser.parse_artifact_page(html, title, url)
        artifact.fetched_at = datetime.now().isoformat()

        storage.save_artifact(artifact)
        return True

    except Exception as e:
        logger.error(f"爬取圣遗物失败 {title}: {e}")
        storage.save_failed_artifact(title, str(e))
        return False


def main():
    """主函数"""
    setup_logging()
    logger.info("=" * 50)
    logger.info("开始圣遗物爬取任务")
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

    parser = ArtifactsParser(base_url=mw_config["base_url"])
    storage = ArtifactStorage(base_dir=storage_config.get("artifact_dir", "storage/artifacts"))

    # 获取已保存和已失败的圣遗物
    saved_artifacts = storage.load_saved_artifacts()
    failed_artifacts = storage.load_failed_artifacts()
    logger.info(f"已保存 {len(saved_artifacts)} 套，已失败 {len(failed_artifacts)} 套")

    # 爬取圣遗物列表
    artifact_links = crawl_artifact_list(client, parser, storage)

    # 过滤已保存和已失败的
    artifacts_to_crawl = [
        link for link in artifact_links
        if link["title"] not in saved_artifacts
        and link["title"] not in failed_artifacts
    ]
    logger.info(f"待爬取 {len(artifacts_to_crawl)} 套")

    # 爬取每套圣遗物
    success_count = 0
    for link in artifacts_to_crawl:
        if crawl_single_artifact(client, parser, storage, link["title"]):
            success_count += 1

    logger.info("=" * 50)
    logger.info(f"爬取完成！成功 {success_count}/{len(artifacts_to_crawl)} 套")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
