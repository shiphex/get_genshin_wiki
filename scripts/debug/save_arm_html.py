#!/usr/bin/env python3
"""保存武器 HTML 以供分析"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crawler.client import MediaWikiClient

client = MediaWikiClient(
    api_url="https://wiki.biligame.com/ys/api.php",
    base_url="https://wiki.biligame.com/ys/",
    request_interval=5,
    timeout=30,
    max_retries=3,
)

title = "狼的武功歌"
html = client.get_page_html(title)

# 保存到 tests/output/
output_dir = Path(__file__).parent.parent.parent / "tests" / "output"
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "test_arm_output.html"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(html)

print(f"HTML 已保存到: {output_file}")
print(f"HTML 长度: {len(html)}")
