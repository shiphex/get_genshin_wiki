#!/usr/bin/env python3
"""单件武器测试脚本"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crawler.client import MediaWikiClient
from src.parser.arms_parser import ArmsParser
from src.storage.arms_writer import ArmStorage


def main():
    client = MediaWikiClient(
        api_url="https://wiki.biligame.com/ys/api.php",
        base_url="https://wiki.biligame.com/ys/",
        request_interval=5,
        timeout=30,
        max_retries=3,
    )

    parser = ArmsParser()
    storage = ArmStorage()

    title = "狼的武功歌"
    html = client.get_page_html(title)
    arm = parser.parse_arm_page(html, title, f"{client.base_url}{title}")

    # 保存到 tests/output/
    output_dir = Path(__file__).parent.parent.parent / "tests" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    output = output_dir / "test_arm_result.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(arm.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"结果已保存到: {output}")
    print(f"名称: {arm.info.名称}")
    print(f"稀有度: {arm.info.稀有度}")
    print(f"性能描述: {arm.info.性能描述文本}")
    print(f"武器技能: {arm.info.武器技能}")
    print(f"技能描述: {arm.info.武器技能文本描述}")
    print(f"武器介绍: {arm.info.武器介绍[:50]}..." if arm.info.武器介绍 else "武器介绍: 无")
    print(f"突破材料: {arm.info.突破材料}")
    print(f"获取途径: {arm.info.获取途径}")
    print(f"武器类型: {arm.info.武器类型}")
    print(f"武器TAG: {arm.info.武器TAG}")
    print(f"故事: {arm.info.故事[:50]}..." if arm.info.故事 else "故事: 无")


if __name__ == "__main__":
    main()
