from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload
from tests.test_parser import SAMPLE_ARCHON_TEMPLATE_OPTION_WIKITEXT
from tools.generate_archon_quest_index import run_generate_index

FIRST_ARCHON_QUEST_WIKITEXT = """{{任务
|任务名称=流浪者的足迹
|任务描述=在陌生的世界醒来。
|任务地区=蒙德
|任务类型=魔神任务
|后续任务=*[[鸟瞰风物]]
|任务流程=*继续前进
}}
==任务剧情==
*派蒙：出发吧。
"""

ARCHON_LIST_WIKITEXT = """== [[流浪者的足迹]] ==
== [[序章]] 捕风的异乡人 ==
{{图标|任务|蒙德|1|序章 第一幕|捕风的异乡人}}
"""

SERIES_ARCHON_WIKITEXT = """{{系列任务
|系列任务名=捕风的异乡人
|副标题=序章 第一幕
|任务类型=魔神任务
|任务地区=蒙德
|系列任务=序章
}}"""


class GenerateArchonQuestIndexTests(unittest.TestCase):
    """Tests for the archon quest index generation tool."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)
        self.store = JsonFileStore(self.data_root)
        self.output_path = self.data_root / "archon_quest_index.json"
        self.store.write("pages", "魔神任务", build_page_payload("魔神任务", ARCHON_LIST_WIKITEXT, page_id=1))
        self.store.write("pages", "流浪者的足迹", build_page_payload("流浪者的足迹", FIRST_ARCHON_QUEST_WIKITEXT, page_id=2))
        self.store.write("pages", "捕风的异乡人", build_page_payload("捕风的异乡人", SERIES_ARCHON_WIKITEXT, page_id=3))
        self.store.write("pages", "鸟瞰风物", build_page_payload("鸟瞰风物", SAMPLE_ARCHON_TEMPLATE_OPTION_WIKITEXT, page_id=4))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_generate_index_writes_required_fields_and_includes_first_quest(self) -> None:
        with patch(
            "tools.generate_archon_quest_index.MediaWikiClient.fetch_rendered_section_titles",
            return_value=["鸟瞰风物"],
        ):
            report = run_generate_index(
                data_root=self.data_root,
                output_path=self.output_path,
                list_title="魔神任务",
            )

        written = json.loads(self.output_path.read_text(encoding="utf-8"))

        self.assertEqual(2, report["quest_count"])
        self.assertEqual(2, written["quest_count"])

        first_entry = written["index"][0]
        second_entry = written["index"][1]
        required_fields = {
            "title",
            "chapter",
            "chapter_name",
            "act",
            "act_name",
            "series_title",
            "前置任务名称",
            "后续任务名称",
        }

        self.assertEqual("流浪者的足迹", first_entry["title"])
        self.assertEqual(required_fields, set(first_entry.keys()))
        self.assertEqual("", first_entry["chapter"])
        self.assertEqual("", first_entry["chapter_name"])
        self.assertEqual("", first_entry["act"])
        self.assertEqual("", first_entry["act_name"])
        self.assertEqual("", first_entry["series_title"])
        self.assertEqual("", first_entry["前置任务名称"])
        self.assertEqual("鸟瞰风物", first_entry["后续任务名称"])

        self.assertEqual("鸟瞰风物", second_entry["title"])
        self.assertEqual(required_fields, set(second_entry.keys()))
        self.assertEqual("序章", second_entry["chapter"])
        self.assertEqual("捕风的异乡人", second_entry["chapter_name"])
        self.assertEqual("第一幕", second_entry["act"])
        self.assertEqual("捕风的异乡人", second_entry["act_name"])
        self.assertEqual("捕风的异乡人", second_entry["series_title"])
        self.assertEqual("流浪者的足迹", second_entry["前置任务名称"])
        self.assertEqual("异常的权柄", second_entry["后续任务名称"])


if __name__ == "__main__":
    unittest.main()
