#!/usr/bin/env python3
"""测试武器列表爬取"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crawler.client import MediaWikiClient
from src.parser.arms_parser import ArmsParser


def main():
    client = MediaWikiClient(
        api_url="https://wiki.biligame.com/ys/api.php",
        base_url="https://wiki.biligame.com/ys/",
        request_interval=5,
        timeout=30,
        max_retries=3,
    )

    parser = ArmsParser()

    # 获取武器图鉴页面
    html = client.get_page_html("武器图鉴")
    links = parser.extract_arm_links(html)

    # 保存到 tests/output/
    output_dir = Path(__file__).parent.parent.parent / "tests" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    links_file = output_dir / "test_arm_links.json"
    with open(links_file, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)

    print(f"找到 {len(links)} 件武器，已保存到: {links_file}")
    for link in links:
        print(f"  - {link['title']}: {link['url']}")


if __name__ == "__main__":
    main()
