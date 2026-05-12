"""
CLI 单元测试
============

测试命令行接口的各项功能：
- crawl category-pages：批量抓取分类页面（支持数量限制和持久化）
- parse character：解析角色页面并持久化结果
- store 命令组：put/query/update/add/delete 完整流程测试

测试方法
--------
- 使用 FakeClient 模拟 API 客户端
- 使用 CliRuntime 注入测试依赖
- 捕获 stdout 进行输出验证
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from get_genshin_wiki.cli import CliRuntime, main
from get_genshin_wiki.crawler import WikiCrawler
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload
from tests.test_parser import SPECIALIZED_PAGE_CASES

# 测试用角色 wikitext
SAMPLE_CHARACTER_WIKITEXT = """{{角色资料|名字=哥伦比娅|元素=水|武器=法器|神之眼描述=三相月临}}
哥伦比娅是愚人众执行官之一。

{{角色天赋|名称=低语之歌|描述=造成水元素伤害|类别=普通攻击|元素=水}}
{{角色/故事|角色详细=白天还是夜晚？<br>那当然是夜晚。|角色故事1=最先听到的是歌声。|冒险笔记名称=月光织就的眼罩|冒险笔记内容=她相信梦境会说真话。|其他=三相月临|其他故事=在获得「三月的权能」之后，她开始思考自己该如何使用它。|结尾=终}}
{{角色展示|壹·人物={{切换板|显示内容}}月下白鸽，何以为家？{{切换板|内容结束}}|贰·故事={{切换板|默认显示|她的过去}}{{切换板|显示内容}}[[file:角色哥伦比娅官方故事图3.jpg|thumb|240px|哥伦比娅官方故事图]]过去像潮汐一样回响。{{切换板|内容结束}}}}
[[Category:角色]]
"""

SAMPLE_VOICE_WIKITEXT = """{{面包屑|哥伦比娅|角色语音}}{{角色导航}}{{语音tab样式}}
<div class="resp-tabs-container">
<div class="resp-tab-content" style="display:block;">
{{角色/语音1|语音类型=闲聊·歌|语音内容=我的歌并不为谁而唱。}}
</div>
<div class="resp-tab-content" style="display:none;">
{{角色/语音|语音类型=无效示例|语音内容日语=無視する}}
</div>
</div>
"""


class FakeClient:
    """
    模拟 MediaWikiClient，用于 CLI 测试。

    记录 API 访问次数和请求的页面列表。
    """

    def __init__(self) -> None:
        self.allowed_checks = 0  # assert_api_allowed 调用次数
        self.page_requests: list[str] = []  # 请求过的页面列表

    def assert_api_allowed(self) -> None:
        """记录 API 权限检查调用。"""
        self.allowed_checks += 1

    def list_categories(self, prefix: str | None = None) -> list[str]:
        """返回预设分类列表。"""
        return ["角色"] if prefix is None else [prefix]

    def list_category_members(self, category_name: str) -> list[str]:
        """返回预设分类成员列表。"""
        return ["哥伦比娅", "阿蕾奇诺"]

    def fetch_page_payload(self, title: str) -> dict:
        """返回预设页面 payload 并记录请求。"""
        self.page_requests.append(title)
        return build_page_payload(title, f"{title} 的正文", page_id=len(self.page_requests))


class CliTests(unittest.TestCase):
    """CLI 单元测试类。"""

    def setUp(self) -> None:
        """创建临时目录和 CLI 运行时环境。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = JsonFileStore(Path(self.temp_dir.name))
        self.client = FakeClient()
        self.runtime = CliRuntime(
            store=self.store,
            client=self.client,
            crawler=WikiCrawler(client=self.client, store=self.store),
            parser=WikiTextParser(),
        )

    def tearDown(self) -> None:
        """清理临时目录。"""
        self.temp_dir.cleanup()

    def run_cli(self, argv: list[str]) -> tuple[int, object]:
        """
        执行 CLI 命令并捕获输出。

        参数
        ----
        argv : list[str]
            命令行参数列表

        返回
        ----
        tuple[int, object]
            (退出码, JSON 解析后的输出)
        """
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(argv, runtime=self.runtime)
        output = stdout.getvalue().strip()
        parsed = json.loads(output) if output else None
        return exit_code, parsed

    def test_crawl_category_pages_respects_limit_and_persists_pages(self) -> None:
        """
        测试 crawl category-pages 命令：
        1. 正确遵守 page-limit 限制
        2. 只请求指定数量的页面
        3. 检查 API 权限
        4. 持久化结果到存储
        """
        exit_code, output = self.run_cli(["crawl", "category-pages", "角色", "--page-limit", "1"])

        self.assertEqual(0, exit_code)
        self.assertEqual(1, len(output))
        self.assertEqual("哥伦比娅", output[0]["title"])
        self.assertEqual(["哥伦比娅"], self.client.page_requests)
        self.assertEqual(1, self.client.allowed_checks)
        self.assertTrue(self.store.exists("pages", "哥伦比娅"))
        self.assertFalse(self.store.exists("pages", "阿蕾奇诺"))

    def test_parse_character_reads_page_payload_and_persists_result(self) -> None:
        """
        测试 parse character 命令：
        1. 从存储读取原始 payload
        2. 解析角色信息
        3. 持久化解析结果到 parsed/characters 命名空间
        """
        # 先写入原始页面数据
        self.store.write("pages", "哥伦比娅", build_page_payload("哥伦比娅", SAMPLE_CHARACTER_WIKITEXT, page_id=7))
        self.store.write("pages", "哥伦比娅语音", build_page_payload("哥伦比娅语音", SAMPLE_VOICE_WIKITEXT, page_id=8))

        exit_code, output = self.run_cli(["parse", "character", "哥伦比娅"])

        self.assertEqual(0, exit_code)
        self.assertEqual("水", output["attributes"]["元素"])
        self.assertEqual("闲聊·歌", output["voice_records"][0]["title"])
        self.assertTrue(self.store.exists("parsed/characters", "哥伦比娅"))

    def test_parse_specialized_commands_persist_results(self) -> None:
        """测试新增的 7 个 parse 子命令及其默认输出命名空间。"""
        case_lookup = {case["title"]: case for case in SPECIALIZED_PAGE_CASES}
        command_cases = [
            ("food", "花果草糖", "parsed/foods", "特殊料理"),
            ("wildlife", "无奇巨斧鱼", "parsed/wildlife", "钓鱼信息"),
            ("questitem", "装有信件的漂流瓶", "parsed/quest-items", "内容"),
            ("item", "奇特的「留影机」", "parsed/items", "来源"),
            ("material", "混沌枢纽", "parsed/materials", "用途"),
            ("name-card", "蒙德·望楼", "parsed/namecards", "获取方式"),
            ("secretitem", "月童的库藏", "parsed/secret-items", "掉落"),
        ]

        for page_id, (command, title, namespace, field_name) in enumerate(command_cases, start=20):
            with self.subTest(command=command, title=title):
                case = case_lookup[title]
                self.store.write("pages", title, build_page_payload(title, case["wikitext"], page_id=page_id))

                exit_code, output = self.run_cli(["parse", command, title])

                self.assertEqual(0, exit_code)
                self.assertEqual(case["assertions"][field_name], output[field_name])
                self.assertTrue(self.store.exists(namespace, title))

    def test_parse_character_story_reads_page_payload_and_persists_story_result(self) -> None:
        """
        测试 parse character-story 命令：
        1. 从存储读取原始 payload
        2. 聚合角色故事相关内容
        3. 持久化结果到 parsed/character-stories 命名空间
        """
        self.store.write("pages", "哥伦比娅", build_page_payload("哥伦比娅", SAMPLE_CHARACTER_WIKITEXT, page_id=7))
        self.store.write("pages", "哥伦比娅语音", build_page_payload("哥伦比娅语音", SAMPLE_VOICE_WIKITEXT, page_id=8))

        exit_code, output = self.run_cli(["parse", "character-story", "哥伦比娅"])

        self.assertEqual(0, exit_code)
        self.assertEqual("三相月临", output["god_eye_description"])
        self.assertEqual("角色详细", output["story_records"][0]["title"])
        self.assertEqual("闲聊·歌", output["voice_records"][0]["title"])
        self.assertTrue(self.store.exists("parsed/character-stories", "哥伦比娅"))

    def test_store_commands_cover_put_query_update_add_and_delete(self) -> None:
        """
        测试完整的 store 命令流程：

        1. put    - 创建新记录
        2. query  - 读取记录
        3. update  - 合并更新字典
        4. add     - 添加新键值对
        5. delete  - 删除记录
        """
        # 1. put - 创建记录
        exit_code, output = self.run_cli(
            [
                "store",
                "put",
                "characters",
                "哥伦比娅",
                "--payload",
                '{"name":"哥伦比娅"}',
            ]
        )
        self.assertEqual(0, exit_code)
        self.assertEqual("characters", output["namespace"])

        # 2. query - 读取记录
        _, output = self.run_cli(["store", "query", "characters", "哥伦比娅"])
        self.assertEqual({"name": "哥伦比娅"}, output)

        # 3. update - 合并更新（覆盖已有键，添加新键）
        _, output = self.run_cli(
            [
                "store",
                "update",
                "characters",
                "哥伦比娅",
                "--payload",
                '{"element":"冰"}',
            ]
        )
        self.assertEqual({"name": "哥伦比娅", "element": "冰"}, output)

        # 4. add - 添加新键（不覆盖已有键）
        _, output = self.run_cli(
            [
                "store",
                "add",
                "characters",
                "哥伦比娅",
                "--payload",
                '{"weapon":"法器"}',
            ]
        )
        self.assertEqual({"name": "哥伦比娅", "element": "冰", "weapon": "法器"}, output)

        # 5. delete - 删除记录
        _, output = self.run_cli(["store", "delete", "characters", "哥伦比娅"])
        self.assertTrue(output["deleted"])
        self.assertFalse(self.store.exists("characters", "哥伦比娅"))


if __name__ == "__main__":
    unittest.main()
