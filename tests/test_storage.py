"""
JsonFileStore 单元测试
=======================

测试 JsonFileStore 存储管理器的各项功能：
- 基本 CRUD 操作（创建、读取、删除）
- 文件名规范化（处理非法字符）
- update 合并字典
- add 追加列表/添加字典键（检测冲突）

测试方法
--------
- 使用临时目录作为数据存储
- 每个测试独立，使用 setUp 创建干净的环境
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from get_genshin_wiki.storage import JsonFileStore


class JsonFileStoreTests(unittest.TestCase):
    """JsonFileStore 单元测试类。"""

    def setUp(self) -> None:
        """创建临时目录和存储实例。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = JsonFileStore(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        """清理临时目录。"""
        self.temp_dir.cleanup()

    def test_write_read_exists_delete_and_list_keys(self) -> None:
        """
        测试基本的 CRUD 操作流程。

        写入 -> 读取 -> 检查存在 -> 列出键 -> 删除 -> 确认删除
        """
        payload = {"name": "哥伦比娅", "element": "冰"}

        path = self.store.write("characters", "哥伦比娅", payload)

        self.assertTrue(path.exists())
        self.assertTrue(self.store.exists("characters", "哥伦比娅"))
        self.assertEqual(payload, self.store.read("characters", "哥伦比娅"))
        self.assertEqual([path.name], self.store.list_keys("characters"))
        self.assertTrue(self.store.delete("characters", "哥伦比娅"))
        self.assertFalse(self.store.exists("characters", "哥伦比娅"))

    def test_build_filename_normalizes_invalid_characters(self) -> None:
        """
        测试文件名规范化处理。

        Windows 文件系统禁用的字符应被替换为下划线。
        """
        filename = self.store.build_filename('角色:哥伦比娅/测试?*"')

        self.assertTrue(filename.endswith(".json"))
        self.assertNotIn(":", filename)
        self.assertNotIn("/", filename)
        self.assertNotIn("?", filename)
        self.assertNotIn("*", filename)

    def test_update_merges_json_objects(self) -> None:
        """
        测试 update 方法正确合并字典。

        新值覆盖旧值，但不删除未指定的键。
        """
        self.store.write("characters", "哥伦比娅", {"元素": "冰", "武器": "弓"})

        updated = self.store.update("characters", "哥伦比娅", {"武器": "法器", "地区": "至冬"})

        self.assertEqual({"元素": "冰", "武器": "法器", "地区": "至冬"}, updated)
        self.assertEqual(updated, self.store.read("characters", "哥伦比娅"))

    def test_add_appends_to_lists(self) -> None:
        """
        测试 add 方法正确追加列表元素。

        支持单个元素和列表的追加。
        """
        self.store.write("pages", "角色列表", ["哥伦比娅"])

        updated = self.store.add("pages", "角色列表", ["阿蕾奇诺", "仆人"])

        self.assertEqual(["哥伦比娅", "阿蕾奇诺", "仆人"], updated)

    def test_add_rejects_overwriting_existing_object_keys(self) -> None:
        """
        测试 add 方法拒绝添加已存在的字典键。

        防止意外覆盖数据。
        """
        self.store.write("characters", "哥伦比娅", {"元素": "冰"})

        with self.assertRaises(ValueError):
            self.store.add("characters", "哥伦比娅", {"元素": "风"})


if __name__ == "__main__":
    unittest.main()
