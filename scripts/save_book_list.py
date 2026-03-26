#!/usr/bin/env python3
"""保存书籍列表到文件"""
import sys
import json
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

    # 保存原始 HTML
    html_file = Path(__file__).parent.parent / "test_book_list.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 已保存到: {html_file}")

    # 提取链接
    links = parser.extract_book_links(html)

    # 保存链接列表
    links_file = Path(__file__).parent.parent / "test_book_links.json"
    with open(links_file, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)
    print(f"链接列表已保存到: {links_file}")
    print(f"共找到 {len(links)} 本书籍")


if __name__ == "__main__":
    main()
