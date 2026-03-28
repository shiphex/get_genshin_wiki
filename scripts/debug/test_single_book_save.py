#!/usr/bin/env python3
"""单本书籍测试脚本"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crawler.client import MediaWikiClient
from src.parser.book_parser import BookParser
from src.storage.writer import BookStorage


def main():
    client = MediaWikiClient(
        api_url="https://wiki.biligame.com/ys/api.php",
        base_url="https://wiki.biligame.com/ys/",
        request_interval=5,
        timeout=30,
        max_retries=3,
    )

    parser = BookParser()
    storage = BookStorage()

    title = "终北祷歌集"
    html = client.get_page_html(title)
    book = parser.parse_book_page(html, title, f"{client.base_url}{title}")

    # 保存到文件
    output = Path(__file__).parent.parent / "test_book_result.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(book.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"结果已保存到: {output}")
    print(f"书名: {book.info.name}")
    print(f"卷数: {book.info.volumes_count}")
    print(f"稀有度: {book.info.rarity}")
    print(f"体裁: {book.info.genre}")
    print(f"国家: {book.info.country}")
    print(f"版本: {book.info.version}")
    print(f"相关角色: {book.info.related_characters}")
    print(f"卷数: {len(book.volumes)}")
    for i, vol in enumerate(book.volumes):
        print(f"  卷{i+1}: {vol.title}")
        print(f"    内容长度: {len(vol.content)}")
        print(f"    获取方式: {vol.obtain_method}")


if __name__ == "__main__":
    main()
