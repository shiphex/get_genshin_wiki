from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload
from tests.test_cli import SAMPLE_CHARACTER_WIKITEXT, SAMPLE_VOICE_WIKITEXT
from tests.test_parser import SPECIALIZED_PAGE_CASES
from tools.reparse_and_store import (
    ENTITY_CONFIGS,
    resolve_entity_configs,
    run_batch,
    validate_generic_record,
)


class BatchToolTests(unittest.TestCase):
    """Tests for shared batch tooling helpers."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)
        self.store = JsonFileStore(self.data_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolve_entity_configs_preserves_default_order_for_subset(self) -> None:
        configs = resolve_entity_configs(["books", "weapons"])
        self.assertEqual(["weapons", "books"], [config.entity_id for config in configs])

    def test_validate_generic_record_reports_missing_required_fields(self) -> None:
        config = ENTITY_CONFIGS["weapons"]
        title = "霜结的誓金枝"
        payload = build_page_payload(title, "{{武器属性|类型=弓}}", page_id=1)
        record = {
            "名称": title,
            "类型": "弓",
            "介绍": "由古老的白木打造而成的长弓",
            "突破武器材料序列": ["长夜燧火"],
            "突破高级材料序列": ["焰剑"],
            "突破普通材料序列": [],
            "获取途径": "限定祈愿",
            "锻造材料": "不可锻造获取",
            "精炼材料": "不可使用材料精炼",
            "故事": "",
        }
        self.store.write("pages", title, payload)
        self.store.write("parsed/weapons", title, record)

        result = validate_generic_record(config, title, payload, record, self.store)

        self.assertFalse(result["ok"])
        self.assertIn("field:突破普通材料序列", result["issues"])
        self.assertIn("field:故事", result["issues"])

    def test_validate_generic_record_requires_boss_domain_material_triplet(self) -> None:
        config = ENTITY_CONFIGS["secret-items"]
        title = "待解「弈局」"
        payload = build_page_payload(title, "{{秘境副本|秘境类型=BOSS秘境|难度4掉落={{图标|材料|升扬样本·骑士}}}}", page_id=2)
        record = {
            "名称": title,
            "类型": "BOSS秘境",
            "介绍": "古老的棋局仍在等待最后一次落子。",
            "掉落": {
                "材料1": "升扬样本·骑士",
                "材料2": "",
                "材料3": "升扬样本·王族",
            },
        }
        self.store.write("pages", title, payload)
        self.store.write("parsed/secret-items", title, record)

        result = validate_generic_record(config, title, payload, record, self.store)

        self.assertFalse(result["ok"])
        self.assertIn("掉落:材料2", result["issues"])

    def test_run_batch_parse_only_writes_report_and_validation_summary(self) -> None:
        food_case = next(case for case in SPECIALIZED_PAGE_CASES if case["title"] == "花果草糖")
        self.store.write("category_members", "食物", ["花果草糖"])
        self.store.write("pages", "花果草糖", build_page_payload("花果草糖", food_case["wikitext"], page_id=7))

        report = run_batch(
            data_root=self.data_root,
            entity_ids=["foods"],
            limit=1,
            fetch_pages=False,
            include_pytest=False,
        )

        self.assertEqual("parse-only", report["mode"])
        self.assertEqual(1, report["validation"]["passed"])
        self.assertEqual(0, report["validation"]["failed"])
        self.assertTrue(self.store.exists("parsed/foods", "花果草糖"))
        self.assertTrue(self.store.exists("reports", "todo-batch-report"))

    def test_run_batch_parse_only_for_characters_uses_single_storage_schema(self) -> None:
        self.store.write("category_members", "角色", ["哥伦比娅"])
        self.store.write("pages", "哥伦比娅", build_page_payload("哥伦比娅", SAMPLE_CHARACTER_WIKITEXT, page_id=7))
        self.store.write("pages", "哥伦比娅语音", build_page_payload("哥伦比娅语音", SAMPLE_VOICE_WIKITEXT, page_id=8))

        report = run_batch(
            data_root=self.data_root,
            entity_ids=["characters"],
            limit=1,
            fetch_pages=False,
            include_pytest=False,
        )

        self.assertEqual("parse-only", report["mode"])
        self.assertEqual(1, report["validation"]["passed"])
        self.assertFalse(self.store.exists("parsed/character-stories", "哥伦比娅"))
        stored = self.store.read("parsed/characters", "哥伦比娅")
        self.assertEqual("哥伦比娅", stored["角色"]["名称"])
        self.assertIn("角色语音", stored)


if __name__ == "__main__":
    unittest.main()
