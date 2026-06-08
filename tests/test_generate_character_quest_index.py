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
    PREVIOUS_CHARACTER_QUEST_WIKITEXT,
)
from tools.generate_character_quest_index import run_generate_index

SERIES_CHARACTER_QUEST_WIKITEXT = """{{系列任务
|系列任务名=盐花
|副标题=古闻之章 第一幕
|任务类型=传说任务
|任务地区=璃月
|系列任务=古闻之章
}}"""


def with_categories(payload: dict, *categories: str) -> dict:
    page = next(iter(payload["query"]["pages"].values()))
    page["categories"] = [
        {"title": category if category.startswith(("Category:", "分类:")) else f"Category:{category}"}
        for category in categories
    ]
    return payload


class GenerateCharacterQuestIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)
        self.store = JsonFileStore(self.data_root)
        self.output_path = self.data_root / "character_quest_index.json"

        self.store.write(
            "categories",
            "character-quests",
            {
                "categories": ["传说任务"],
                "category_map": {
                    "传说任务": "传说任务",
                    "部族纪闻": "",
                },
                "probe_results": [],
            },
        )
        self.store.write("category_members", "传说任务", ["盐花", "漩涡之遗", "旧日之影"])
        self.store.write("pages", "传说任务", build_page_payload("传说任务", CHARACTER_QUEST_LIST_WIKITEXT, page_id=1))
        self.store.write(
            "pages",
            "盐花",
            with_categories(build_page_payload("盐花", SERIES_CHARACTER_QUEST_WIKITEXT, page_id=2), "系列任务", "传说任务"),
        )
        self.store.write(
            "pages",
            "旧日之影",
            with_categories(build_page_payload("旧日之影", PREVIOUS_CHARACTER_QUEST_WIKITEXT, page_id=3), "任务", "传说任务"),
        )
        self.store.write(
            "pages",
            "漩涡之遗",
            with_categories(build_page_payload("漩涡之遗", CHARACTER_QUEST_WIKITEXT, page_id=4), "任务", "传说任务"),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_generate_index_orders_leaf_quests_by_prerequisite_chain(self) -> None:
        report = run_generate_index(
            data_root=self.data_root,
            output_path=self.output_path,
            list_title="传说任务",
        )

        written = json.loads(self.output_path.read_text(encoding="utf-8"))

        self.assertEqual(2, report["quest_count"])
        self.assertEqual(2, written["quest_count"])
        self.assertEqual(["旧日之影", "漩涡之遗"], [item["title"] for item in written["index"]])
        self.assertEqual("古闻之章", written["index"][0]["chapter_name"])
        self.assertEqual("第一幕", written["index"][0]["act"])
        self.assertEqual("盐花", written["index"][0]["act_name"])
        self.assertEqual("", written["index"][0]["前置任务"])
        self.assertEqual("漩涡之遗", written["index"][0]["后续任务"])
        self.assertEqual("旧日之影", written["index"][1]["前置任务"])

    def test_run_generate_index_deduplicates_normalized_task_titles(self) -> None:
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
        self.store.write("category_members", "部族纪闻", ["基尼奇的交易（任务）"])
        self.store.write("pages", "传说任务", build_page_payload("传说任务", MODERN_CHARACTER_QUEST_LIST_WIKITEXT, page_id=21))
        self.store.write(
            "pages",
            "基尼奇的交易（任务）",
            with_categories(
                build_page_payload("基尼奇的交易（任务）", MODERN_TRIBAL_QUEST_WIKITEXT, page_id=22),
                "分类:任务",
                "分类:部族纪闻",
            ),
        )

        report = run_generate_index(
            data_root=self.data_root,
            output_path=self.output_path,
            list_title="传说任务",
        )

        written = json.loads(self.output_path.read_text(encoding="utf-8"))

        self.assertEqual(1, report["quest_count"])
        self.assertEqual(1, written["quest_count"])
        self.assertEqual(["基尼奇的交易"], [item["title"] for item in written["index"]])


if __name__ == "__main__":
    unittest.main()
