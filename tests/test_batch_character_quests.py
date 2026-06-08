from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload
from tests.test_character_quest_parser import (
    CHARACTER_QUEST_LIST_WIKITEXT,
    CHARACTER_QUEST_WIKITEXT,
    MODERN_CHARACTER_QUEST_LIST_WIKITEXT,
    MODERN_TRIBAL_QUEST_WIKITEXT,
    TRIBAL_QUEST_WIKITEXT,
)
from tools.batch_character_quests import run_batch

SERIES_CHARACTER_QUEST_WIKITEXT = """{{系列任务
|系列任务名=盐花
|副标题=古闻之章 第一幕
|任务类型=传说任务
|任务地区=璃月
|系列任务=古闻之章
}}"""

SERIES_TRIBAL_QUEST_WIKITEXT = """{{系列任务
|系列任务名=神秘岛之旅
|副标题=流泉所归之处 第三幕
|任务类型=部族纪闻
|任务地区=纳塔
|系列任务=流泉所归之处
}}"""


def with_categories(payload: dict, *categories: str) -> dict:
    page = next(iter(payload["query"]["pages"].values()))
    page["categories"] = [
        {"title": category if category.startswith(("Category:", "分类:")) else f"Category:{category}"}
        for category in categories
    ]
    return payload


class BatchCharacterQuestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)
        self.store = JsonFileStore(self.data_root)
        self.output_path = self.data_root / "character_quests.json"

        self.store.write(
            "categories",
            "character-quests",
            {
                "categories": ["传说任务", "部族纪闻"],
                "category_map": {
                    "传说任务": "传说任务",
                    "部族纪闻": "部族纪闻",
                },
                "probe_results": [],
            },
        )
        self.store.write("category_members", "传说任务", ["盐花", "漩涡之遗"])
        self.store.write("category_members", "部族纪闻", ["神秘岛之旅", "值得托付之人"])
        self.store.write("pages", "传说任务", build_page_payload("传说任务", CHARACTER_QUEST_LIST_WIKITEXT, page_id=1))
        self.store.write(
            "pages",
            "盐花",
            with_categories(build_page_payload("盐花", SERIES_CHARACTER_QUEST_WIKITEXT, page_id=2), "系列任务", "传说任务"),
        )
        self.store.write(
            "pages",
            "漩涡之遗",
            with_categories(build_page_payload("漩涡之遗", CHARACTER_QUEST_WIKITEXT, page_id=3), "任务", "传说任务"),
        )
        self.store.write(
            "pages",
            "神秘岛之旅",
            with_categories(build_page_payload("神秘岛之旅", SERIES_TRIBAL_QUEST_WIKITEXT, page_id=4), "系列任务", "部族纪闻"),
        )
        self.store.write(
            "pages",
            "值得托付之人",
            with_categories(build_page_payload("值得托付之人", TRIBAL_QUEST_WIKITEXT, page_id=5), "任务", "部族纪闻"),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_batch_writes_leaf_records_and_group_index(self) -> None:
        report = run_batch(
            data_root=self.data_root,
            output_path=self.output_path,
            list_title="传说任务",
            resume=False,
        )

        written = json.loads(self.output_path.read_text(encoding="utf-8"))

        self.assertEqual(["传说任务", "部族纪闻"], report["categories"])
        self.assertEqual(2, report["quest_count"])
        self.assertTrue(self.store.exists("parsed/character-quests", "漩涡之遗"))
        self.assertTrue(self.store.exists("parsed/character-quests", "值得托付之人"))
        self.assertFalse(self.store.exists("parsed/character-quests", "盐花"))
        self.assertFalse(self.store.exists("parsed/character-quests", "神秘岛之旅"))
        self.assertEqual(["漩涡之遗", "值得托付之人"], [item["任务名称"] for item in written["quests"]])
        self.assertEqual(
            [
                {"title": "盐花", "tasks": ["漩涡之遗"]},
                {"title": "神秘岛之旅", "tasks": ["值得托付之人"]},
            ],
            [{"title": item["title"], "tasks": item["tasks"]} for item in written["index"]],
        )

    def test_run_batch_filters_series_pages_with_chinese_category_prefix_and_normalizes_titles(self) -> None:
        output_path = self.data_root / "modern_character_quests.json"
        self.store.write(
            "categories",
            "character-quests",
            {
                "categories": ["部族纪闻"],
                "category_map": {
                    "传说任务": "",
                    "部族纪闻": "部族纪闻",
                },
                "probe_results": [],
            },
        )
        self.store.write("category_members", "部族纪闻", ["基尼奇的交易（系列任务）", "基尼奇的交易（任务）"])
        self.store.write("pages", "传说任务", build_page_payload("传说任务", MODERN_CHARACTER_QUEST_LIST_WIKITEXT, page_id=11))
        self.store.write(
            "pages",
            "基尼奇的交易（系列任务）",
            with_categories(
                build_page_payload(
                    "基尼奇的交易（系列任务）",
                    """{{系列任务
|系列任务名=基尼奇的交易
|副标题=尤潘基的回火 第三幕
|任务类型=部族纪闻
|任务地区=纳塔
|系列任务=尤潘基的回火
}}""",
                    page_id=12,
                ),
                "分类:系列任务",
                "分类:部族纪闻",
            ),
        )
        self.store.write(
            "pages",
            "基尼奇的交易（任务）",
            with_categories(
                build_page_payload("基尼奇的交易（任务）", MODERN_TRIBAL_QUEST_WIKITEXT, page_id=13),
                "分类:任务",
                "分类:部族纪闻",
            ),
        )

        report = run_batch(
            data_root=self.data_root,
            output_path=output_path,
            list_title="传说任务",
            resume=False,
        )

        written = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(1, report["quest_count"])
        self.assertTrue(self.store.exists("parsed/character-quests", "基尼奇的交易"))
        self.assertFalse(self.store.exists("parsed/character-quests", "基尼奇的交易（任务）"))
        self.assertFalse(self.store.exists("parsed/character-quests", "基尼奇的交易（系列任务）"))
        self.assertEqual(["基尼奇的交易"], [item["任务名称"] for item in written["quests"]])
        self.assertEqual("第三幕", written["quests"][0]["所属幕"])
        self.assertEqual("基尼奇的交易", written["quests"][0]["所属任务"])


if __name__ == "__main__":
    unittest.main()
