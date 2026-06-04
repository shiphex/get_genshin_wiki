from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload
from tests.test_parser import SAMPLE_ARCHON_TEMPLATE_OPTION_WIKITEXT
from tools.batch_archon_quests import run_batch

SINGLE_ARCHON_LIST_WIKITEXT = """== [[序章]] 捕风的异乡人 ==
{{图标|任务|蒙德|1|序章 第一幕|捕风的异乡人}}
"""

SERIES_ARCHON_WIKITEXT = """{{系列任务
|系列任务名=捕风的异乡人
|副标题=序章 第一幕
|任务类型=魔神任务
|任务地区=蒙德
|系列任务=序章
}}"""


class BatchArchonQuestTests(unittest.TestCase):
    """Tests for the archon quest batch parsing tool."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)
        self.store = JsonFileStore(self.data_root)
        self.output_path = self.data_root / "archon_quests.json"
        self.store.write("pages", "魔神任务", build_page_payload("魔神任务", SINGLE_ARCHON_LIST_WIKITEXT, page_id=1))
        self.store.write("pages", "捕风的异乡人", build_page_payload("捕风的异乡人", SERIES_ARCHON_WIKITEXT, page_id=2))
        self.store.write("pages", "鸟瞰风物", build_page_payload("鸟瞰风物", SAMPLE_ARCHON_TEMPLATE_OPTION_WIKITEXT, page_id=3))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_batch_writes_output_and_parsed_records(self) -> None:
        with patch(
            "tools.batch_archon_quests.MediaWikiClient.fetch_rendered_section_titles",
            return_value=["鸟瞰风物"],
        ):
            report = run_batch(
                data_root=self.data_root,
                output_path=self.output_path,
                list_title="魔神任务",
                resume=False,
            )

        self.assertEqual(1, report["quest_count"])
        self.assertTrue(self.store.exists("parsed/archon-quests", "鸟瞰风物"))
        stored = self.store.read("parsed/archon-quests", "鸟瞰风物")
        written = json.loads(self.output_path.read_text(encoding="utf-8"))

        self.assertEqual("序章", stored["章节"])
        self.assertEqual("捕风的异乡人", stored["章节名称"])
        self.assertEqual("第一幕", stored["幕"])
        self.assertEqual("捕风的异乡人", stored["幕名称"])
        self.assertEqual(["前往低语森林", "寻找安柏"], stored["任务流程"])
        self.assertEqual("", stored["对话"][0]["所属任务流程"])
        self.assertIn("相关角色", stored)
        self.assertNotIn("相关NPC", stored)
        self.assertEqual("鸟瞰风物", written["quests"][0]["任务标题"]["中文"])
        self.assertEqual("捕风的异乡人", written["index"][0]["act_name"])
        self.assertEqual("捕风的异乡人", written["index"][0]["series_title"])

    def test_run_batch_resume_uses_existing_output_records(self) -> None:
        with patch(
            "tools.batch_archon_quests.MediaWikiClient.fetch_rendered_section_titles",
            return_value=["鸟瞰风物"],
        ):
            run_batch(
                data_root=self.data_root,
                output_path=self.output_path,
                list_title="魔神任务",
                resume=False,
            )
        self.store.delete("pages", "鸟瞰风物")

        with patch(
            "tools.batch_archon_quests.MediaWikiClient.fetch_rendered_section_titles",
            return_value=["鸟瞰风物"],
        ):
            report = run_batch(
                data_root=self.data_root,
                output_path=self.output_path,
                list_title="魔神任务",
                resume=True,
            )

        self.assertEqual(1, report["quest_count"])
        written = json.loads(self.output_path.read_text(encoding="utf-8"))
        self.assertEqual(1, written["quest_count"])
        self.assertEqual(["鸟瞰风物"], [item["任务标题"]["中文"] for item in written["quests"]])


if __name__ == "__main__":
    unittest.main()
