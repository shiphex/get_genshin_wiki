#!/usr/bin/env python3
"""书籍爬取脚本"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawler.client import MediaWikiClient
from src.parser.book_parser import BookParser
from src.storage.writer import BookStorage
from src.utils.config import load_config
from src.utils.logger import setup_logging

logger = logging.getLogger(__name__)


def crawl_book_list(client: MediaWikiClient, parser: BookParser, storage: BookStorage) -> list[dict]:
    """爬取书籍列表页面

    Returns:
        书籍链接列表
    """
    logger.info("获取书籍列表页面...")
    html = client.get_page_html("书籍一览")
    links = parser.extract_book_links(html)
    logger.info(f"找到 {len(links)} 本书籍")
    return links


def crawl_single_book(client: MediaWikiClient, parser: BookParser, storage: BookStorage, title: str) -> bool:
    """爬取单本书籍

    Returns:
        是否成功
    """
    try:
        logger.info(f"爬取书籍: {title}")
        html = client.get_page_html(title)
        url = f"{client.base_url}{title}"

        book = parser.parse_book_page(html, title, url)
        book.fetched_at = datetime.now().isoformat()

        storage.save_book(book)
        return True

    except Exception as e:
        logger.error(f"爬取书籍失败 {title}: {e}")
        storage.save_failed_book(title, str(e))
        return False


def main():
    """主函数"""
    setup_logging()
    logger.info("=" * 50)
    logger.info("开始书籍爬取任务")
    logger.info("=" * 50)

    # 加载配置
    config = load_config()
    mw_config = config["mediawiki"]
    storage_config = config.get("storage", {})

    # 初始化组件
    client = MediaWikiClient(
        api_url=mw_config["api_url"],
        base_url=mw_config["base_url"],
        request_interval=mw_config.get("request_interval", 5),
        timeout=mw_config.get("timeout", 30),
        max_retries=mw_config.get("max_retries", 3),
        user_agent=mw_config.get("user_agent", "get_wiki_genshin/0.1.0"),
    )

    parser = BookParser(base_url=mw_config["base_url"])
    storage = BookStorage(base_dir=storage_config.get("book_dir", "storage/book"))

    # 获取已保存和已失败的书籍
    saved_books = storage.load_saved_books()
    failed_books = storage.load_failed_books()
    logger.info(f"已保存 {len(saved_books)} 本，已失败 {len(failed_books)} 本")

    # 爬取书籍列表
    book_links = crawl_book_list(client, parser, storage)

    # 过滤已保存和已失败的
    books_to_crawl = [
        link for link in book_links
        if link["title"] not in saved_books
        and link["title"] not in failed_books
    ]
    logger.info(f"待爬取 {len(books_to_crawl)} 本")

    # 爬取每本书
    success_count = 0
    for link in books_to_crawl:
        if crawl_single_book(client, parser, storage, link["title"]):
            success_count += 1

    logger.info("=" * 50)
    logger.info(f"爬取完成！成功 {success_count}/{len(books_to_crawl)} 本")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
