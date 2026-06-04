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

from get_genshin_wiki.cli import CliRuntime, build_parser, main
from get_genshin_wiki.crawler import WikiCrawler
from get_genshin_wiki.parser import WikiTextParser
from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload
from tests.test_parser import (
    SAMPLE_ARCHON_ICON_LIST_WIKITEXT,
    SAMPLE_ARCHON_TEMPLATE_OPTION_WIKITEXT,
    (
    SAMPLE_BOOK_WIKITEXT,
    SAMPLE_CHRONICLE_WIKITEXT,
    SAMPLE_EVENT_PAGE_WIKITEXT,
    SAMPLE_EVENT_QUEST_WIKITEXT,
    SPECIALIZED_PAGE_CASES,
),
)

# 测试用角色 wikitext
SAMPLE_CHARACTER_WIKITEXT = """{{角色资料|名字=哥伦比娅|称号=空月归乡|所属=挪德卡莱|介绍=于挪德卡莱诞生的「月之少女」。|元素=水|武器=法器|神之眼描述=三相月临|命之座=御月鸽座}}
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

SAMPLE_WEAPON_WIKITEXT = """{{武器属性|名字=霜结的誓金枝|类型=弓|介绍=由古老的白木打造而成的长弓|获取途径=[[限定祈愿]]|是否可锻造获取=否}}
{{武器突破|突破武器材料1=长夜燧火|突破高级材料1=焰剑|突破普通材料1=执凭}}
{{武器故事|故事=在遥古的岁月，曾有牧歌与繁花统治无忧的乡野。}}
[[Category:武器]]
"""

SAMPLE_ARTIFACT_WIKITEXT = """{{圣遗物属性|套装名称=风起之日|获取方式={{圣遗物套装/获取途径|BOSS|(四星)击杀首领或周本BOSS}}|时之沙名称=春律的片刻|时之沙描述=时之沙描述文本|时之沙故事=时之沙故事文本|死之羽名称=晨光的明誓|死之羽描述=死之羽描述文本|死之羽故事=死之羽故事文本|理之冠名称=哀慕的恋歌|理之冠描述=理之冠描述文本|理之冠故事=理之冠故事文本|生之花名称=风花的箴铭|生之花描述=生之花描述文本|生之花故事=生之花故事文本|空之杯名称=未言的宴话|空之杯描述=空之杯描述文本|空之杯故事=空之杯故事文本}}
[[Category:圣遗物]]
"""

SAMPLE_MONSTER_WIKITEXT = """{{怪物信息|怪物类别=周刷BOSS|怪物分类=值得铭记的强敌|怪物类型=其他|出现地点=蒙德·风起地|掉落素材=BOSS|BOSS素材=升扬样本·骑士,升扬样本·战车,升扬样本·王族}}
集魔女会诸家技艺而制成的集团军。

== 介绍 ==
这是怪物的介绍内容。
"""


class FakeClient:
    """
    模拟 MediaWikiClient，用于 CLI 测试。

    记录 API 访问次数和请求的页面列表。
    """

    def __init__(self) -> None:
        self.allowed_checks = 0  # assert_api_allowed 调用次数
        self.page_requests: list[str] = []  # 请求过的页面列表
        self.categories = ["角色", "活动事件"]
        self.category_members = {
            "角色": ["哥伦比娅", "阿蕾奇诺"],
            "活动事件": ["有朋自远方来·其二"],
        }
        self.page_payloads: dict[str, dict] = {}

    def assert_api_allowed(self) -> None:
        """记录 API 权限检查调用。"""
        self.allowed_checks += 1

    def list_categories(self, prefix: str | None = None) -> list[str]:
        """返回预设分类列表。"""
        if prefix in {"提瓦特", "公元", "编年"}:
            return []
        if prefix is None:
            return list(self.categories)
        return [name for name in self.categories if name.startswith(prefix)]

    def list_category_members(self, category_name: str) -> list[str]:
        """返回预设分类成员列表。"""
        if category_name in {"提瓦特编年史", "提瓦特编年史（公元纪）", "公元纪"}:
            return []
        return list(self.category_members.get(category_name, []))

    def fetch_page_payload(self, title: str) -> dict:
        """返回预设页面 payload 并记录请求。"""
        self.page_requests.append(title)
        if title == "提瓦特编年史（公元纪）":
            return build_page_payload(title, SAMPLE_CHRONICLE_WIKITEXT, page_id=len(self.page_requests))
        if title == "提瓦特编年史":
            return build_page_payload(title, "#重定向 [[提瓦特编年史（公元纪）]]", page_id=len(self.page_requests))
        if title == "编年史":
            return build_page_payload(title, "#重定向 [[提瓦特编年史]]", page_id=len(self.page_requests))
        if title in self.page_payloads:
            return self.page_payloads[title]
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

    def test_crawl_chronicle_pages_falls_back_to_page_probe_and_persists_pages(self) -> None:
        """测试 crawl chronicle-pages 会回退到页面探测并抓取编年史页面。"""
        exit_code, output = self.run_cli(["crawl", "chronicle-pages", "--page-limit", "1"])

        self.assertEqual(0, exit_code)
        self.assertEqual("page", output["source_type"])
        self.assertEqual("", output["category_name"])
        self.assertEqual(["提瓦特编年史（公元纪）"], output["page_titles"])
        self.assertEqual(1, len(output["pages"]))
        self.assertEqual("提瓦特编年史（公元纪）", output["pages"][0]["title"])
        self.assertEqual(["提瓦特编年史（公元纪）", "提瓦特编年史（公元纪）"], self.client.page_requests)
        self.assertEqual(1, self.client.allowed_checks)
        self.assertTrue(self.store.exists("pages", "提瓦特编年史（公元纪）"))

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
        self.assertEqual("哥伦比娅", output["角色"]["名称"])
        self.assertEqual("水", output["角色"]["元素属性"])
        self.assertEqual("闲聊·歌", next(iter(output["角色语音"].keys())))
        self.assertEqual("我的歌并不为谁而唱。", output["角色语音"]["闲聊·歌"])
        self.assertNotIn("title", output)
        self.assertTrue(self.store.exists("parsed/characters", "哥伦比娅"))
        self.assertFalse(self.store.exists("parsed/character-stories", "哥伦比娅"))

    def test_parse_archon_quest_reads_page_payload_and_persists_result(self) -> None:
        """测试 parse archon-quest 命令会利用列表页上下文并持久化结果。"""
        self.store.write("pages", "魔神任务", build_page_payload("魔神任务", SAMPLE_ARCHON_ICON_LIST_WIKITEXT, page_id=9))
        self.store.write("pages", "鸟瞰风物", build_page_payload("鸟瞰风物", SAMPLE_ARCHON_TEMPLATE_OPTION_WIKITEXT, page_id=10))

        exit_code, output = self.run_cli(["parse", "archon-quest", "鸟瞰风物"])

        self.assertEqual(0, exit_code)
        self.assertEqual("鸟瞰风物", output["任务标题"]["中文"])
        self.assertEqual("序章", output["章节"])
        self.assertEqual("捕风的异乡人", output["章节名称"])
        self.assertEqual("第一幕", output["幕"])
        self.assertEqual("", output["幕名称"])
        self.assertEqual("option", output["对话"][2]["类型"])
        self.assertEqual(["前往低语森林", "寻找安柏"], output["任务流程"])
        self.assertEqual("", output["对话"][0]["所属任务流程"])
        self.assertIn("相关角色", output)
        self.assertNotIn("相关NPC", output)
        self.assertNotIn("英文", output["任务标题"])
        self.assertNotIn("任务奖励", output)
        self.assertNotIn("奖励摘要", output)
        self.assertNotIn("所属版本", output)
        self.assertTrue(self.store.exists("parsed/archon-quests", "鸟瞰风物"))

    def test_parse_chronicle_reads_page_payload_and_persists_result(self) -> None:
        """测试 parse chronicle 命令会输出并持久化编年史结构。"""
        self.store.write(
            "pages",
            "提瓦特编年史（公元纪）",
            build_page_payload("提瓦特编年史（公元纪）", SAMPLE_CHRONICLE_WIKITEXT, page_id=11),
        )

        exit_code, output = self.run_cli(["parse", "chronicle", "提瓦特编年史（公元纪）"])

        self.assertEqual(0, exit_code)
        self.assertEqual("提瓦特编年史（公元纪）", output["title"])
        self.assertEqual("", output["intro"])
        self.assertEqual(1, len(output["sections"]))
        self.assertEqual("提瓦特公元纪年", output["sections"][0]["title"])
        self.assertEqual("公元前", output["sections"][0]["items"][0]["title"])
        self.assertTrue(self.store.exists("parsed/chronicles", "提瓦特编年史（公元纪）"))
        return
        self.assertEqual("提瓦特编年史（公元纪）", output["title"])
        self.assertEqual(4, len(output["records"]))
        self.assertEqual("公元前", output["records"][1]["year"])
        self.assertTrue(self.store.exists("parsed/chronicles", "提瓦特编年史（公元纪）"))

    def test_crawl_event_quests_discovers_category_and_fetches_related_event_pages(self) -> None:
        """测试 crawl event-quests 会探测活动任务分类并补抓相关活动主页。"""
        self.client.page_payloads["有朋自远方来·其二"] = build_page_payload(
            "有朋自远方来·其二",
            SAMPLE_EVENT_QUEST_WIKITEXT,
            page_id=21,
        )
        self.client.page_payloads["「有朋自远方来」"] = build_page_payload(
            "「有朋自远方来」",
            SAMPLE_EVENT_PAGE_WIKITEXT,
            page_id=22,
        )

        exit_code, output = self.run_cli(["crawl", "event-quests"])

        self.assertEqual(0, exit_code)
        self.assertEqual("活动事件", output["category"])
        self.assertEqual("有朋自远方来·其二", output["quests"][0]["title"])
        self.assertEqual("「有朋自远方来」", output["events"][0]["title"])
        self.assertEqual(["有朋自远方来·其二", "「有朋自远方来」"], self.client.page_requests)
        self.assertEqual(1, self.client.allowed_checks)
        self.assertTrue(self.store.exists("pages", "有朋自远方来·其二"))
        self.assertTrue(self.store.exists("pages", "「有朋自远方来」"))
        self.assertEqual({"category": "活动事件"}, self.store.read("categories", "event-quests"))

    def test_parse_event_quest_uses_related_event_page_and_persists_result(self) -> None:
        """测试 parse event-quest 会读取已存储的活动主页补全活动列表与活动期间。"""
        self.store.write(
            "pages",
            "有朋自远方来·其二",
            build_page_payload("有朋自远方来·其二", SAMPLE_EVENT_QUEST_WIKITEXT, page_id=31),
        )
        self.store.write(
            "pages",
            "「有朋自远方来」",
            build_page_payload("「有朋自远方来」", SAMPLE_EVENT_PAGE_WIKITEXT, page_id=32),
        )

        exit_code, output = self.run_cli(["parse", "eventquest", "有朋自远方来·其二"])

        self.assertEqual(0, exit_code)
        self.assertEqual("「有朋自远方来」", output["活动名称"])
        self.assertEqual("2023/05/11 10:00 ~ 2023/05/22 03:59", output["活动期间"])
        self.assertEqual("望舒客栈近日迎来了一批来自须弥的客人，你和派蒙决定帮言笑招待他们。", output["所属任务描述"])
        self.assertEqual(
            ["有朋自远方来·其一", "有朋自远方来·其二", "有朋自远方来·其三"],
            output["活动列表"],
        )
        self.assertEqual(
            ["与言笑对话", "为等待已久的须弥一行人上菜"],
            output["任务列表"],
        )
        self.assertEqual(["这声音是…", "他们看起来很饿。"], output["剧情对话"][0]["对话"][2]["选项"])
        self.assertTrue(self.store.exists("parsed/event-quests", "有朋自远方来·其二"))

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

    def test_parse_weapon_artifact_monster_and_book_commands_persist_results(self) -> None:
        """测试 parse weapon/artifact/monster/book 的默认输出命名空间。"""
        cases = [
            ("weapon", "霜结的誓金枝", SAMPLE_WEAPON_WIKITEXT, "parsed/weapons", "类型", "弓"),
            ("artifact", "风起之日", SAMPLE_ARTIFACT_WIKITEXT, "parsed/artifacts", "获取方式", "击杀首领或周本BOSS"),
            ("monster", "门扉前的弈局", SAMPLE_MONSTER_WIKITEXT, "parsed/monsters", "monster_class", "周刷BOSS"),
            ("book", "白夜国馆藏", SAMPLE_BOOK_WIKITEXT, "parsed/books", "genre", "史书"),
        ]

        for page_id, (command, title, wikitext, namespace, field_name, expected) in enumerate(cases, start=40):
            with self.subTest(command=command, title=title):
                self.store.write("pages", title, build_page_payload(title, wikitext, page_id=page_id))

                exit_code, output = self.run_cli(["parse", command, title])

                self.assertEqual(0, exit_code)
                self.assertEqual(expected, output[field_name])
                self.assertTrue(self.store.exists(namespace, title))

    def test_parse_character_story_subcommand_is_removed(self) -> None:
        """测试 parse character-story 子命令已移除。"""
        with self.assertRaises(SystemExit) as context:
            build_parser().parse_args(["parse", "character-story", "哥伦比娅"])

        self.assertEqual(2, context.exception.code)

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
