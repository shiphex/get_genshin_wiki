#!/usr/bin/env python3
"""测试书籍列表爬取"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawler.client import MediaWikiClient
from src.parser.book_parser import BookParser


def main():
    client = MediaWikiClient(
        api_url="https://wiki.biligame.com/ys/api.php",
        base_url="https://wiki.biligame.com/ys/",
        request_interval=5,
        timeout=30,
        max_retries=3,
    )

    parser = BookParser()

    # 获取书籍列表页面
    html = client.get_page_html("书籍一览")
    links = parser.extract_book_links(html)

    print(f"找到 {len(links)} 本书籍:")
    for link in links:
        print(f"  - {link['title']}: {link['url']}")


if __name__ == "__main__":
    main()
