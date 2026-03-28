#!/usr/bin/env python3
"""单本书籍测试脚本"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crawler.client import MediaWikiClient
from src.parser.book_parser import BookParser
from src.storage.writer import BookStorage
from src.utils.logger import setup_logging


def main():
    setup_logging("DEBUG")
    logger = logging.getLogger(__name__)

    client = MediaWikiClient(
        api_url="https://wiki.biligame.com/ys/api.php",
        base_url="https://wiki.biligame.com/ys/",
        request_interval=5,
        timeout=30,
        max_retries=3,
    )

    parser = BookParser()
    storage = BookStorage()

    # 测试单本书
    title = "终北祷歌集"
    logger.info(f"获取书籍页面: {title}")

    try:
        html = client.get_page_html(title)
        logger.info(f"HTML 长度: {len(html)}")

        # 解析
        book = parser.parse_book_page(html, title, f"{client.base_url}{title}")

        logger.info(f"书名: {book.info.name}")
        logger.info(f"卷数: {book.info.volumes_count}")
        logger.info(f"稀有度: {book.info.rarity}")
        logger.info(f"体裁: {book.info.genre}")
        logger.info(f"国家: {book.info.country}")
        logger.info(f"版本: {book.info.version}")
        logger.info(f"相关角色: {book.info.related_characters}")
        logger.info(f"获取方式: {book.info.obtain_method}")
        logger.info(f"解析到 {len(book.volumes)} 卷")

        for i, vol in enumerate(book.volumes):
            logger.info(f"  卷 {i+1}: {vol.title}")
            logger.info(f"    内容长度: {len(vol.content)} 字符")
            logger.info(f"    获取方式: {vol.obtain_method}")
            if vol.content:
                logger.info(f"    内容预览: {vol.content[:100]}...")

    except Exception as e:
        logger.error(f"错误: {e}", exc_info=True)


if __name__ == "__main__":
    main()
