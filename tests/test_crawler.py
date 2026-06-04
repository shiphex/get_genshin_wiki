"""
WikiCrawler 单元测试
====================

测试 WikiCrawler 爬虫编排器的各项功能：
- 分类列表抓取与持久化
- 单页面抓取与持久化
- 分类批量抓取及数量限制

测试方法
--------
- 使用 FakeClient 模拟 MediaWikiClient
- 使用临时目录作为数据存储
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from get_genshin_wiki.crawler import WikiCrawler
from get_genshin_wiki.storage import JsonFileStore
from tests.helpers import build_page_payload
from tests.test_parser import SAMPLE_CHRONICLE_WIKITEXT


class FakeClient:
    """
    模拟 MediaWikiClient，用于测试爬虫逻辑。

    提供预设的分类、成员和页面数据。
    """

    def __init__(self) -> None:
        self.page_requests: list[str] = []  # 记录请求过的页面
        self.category_requests: list[str | None] = []  # 记录分类探测请求

    def list_categories(self, prefix: str | None = None) -> list[str]:
        """返回预设的分类列表。"""
        self.category_requests.append(prefix)
        if prefix in {"提瓦特", "公元", "编年"}:
            return []
        return ["角色"] if prefix is None else [prefix]

    def list_category_members(self, category_name: str) -> list[str]:
        """返回预设的分类成员列表。"""
        if category_name in {"提瓦特编年史", "提瓦特编年史（公元纪）", "公元纪"}:
            return []
        return ["哥伦比娅", "阿蕾奇诺"]

    def fetch_page_payload(self, title: str) -> dict:
        """返回预设的页面 payload，并记录请求。"""
        self.page_requests.append(title)
        if title == "提瓦特编年史（公元纪）":
            return build_page_payload(title, SAMPLE_CHRONICLE_WIKITEXT, page_id=77)
        if title == "提瓦特编年史":
            return build_page_payload(title, "#重定向 [[提瓦特编年史（公元纪）]]", page_id=78)
        if title == "编年史":
            return build_page_payload(title, "#重定向 [[提瓦特编年史]]", page_id=79)
        return build_page_payload(title, f"{title} 的正文")


class WikiCrawlerTests(unittest.TestCase):
    """WikiCrawler 单元测试类。"""

    def setUp(self) -> None:
        """创建临时目录和测试所需的组件。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = JsonFileStore(Path(self.temp_dir.name))
        self.client = FakeClient()
        self.crawler = WikiCrawler(self.client, self.store)

    def tearDown(self) -> None:
        """清理临时目录。"""
        self.temp_dir.cleanup()

    def test_crawl_categories_persists_results(self) -> None:
        """
        测试 crawl_categories 抓取后自动持久化到存储。
        """
        categories = self.crawler.crawl_categories()

        self.assertEqual(["角色"], categories)
        self.assertTrue(self.store.list_keys("categories"))

    def test_crawl_page_persists_payload(self) -> None:
        """
        测试 crawl_page 抓取页面后自动持久化。
        """
        payload = self.crawler.crawl_page("哥伦比娅")

        self.assertEqual("哥伦比娅", payload["query"]["pages"]["1"]["title"])
        self.assertTrue(self.store.exists("pages", "哥伦比娅"))

    def test_crawl_category_pages_honours_limit(self) -> None:
        """
        测试 crawl_category_pages 正确遵守 page_limit 限制。

        只抓取指定数量的页面，不过度请求。
        """
        paths = self.crawler.crawl_category_pages("角色", page_limit=1)

        self.assertEqual(1, len(paths))
        self.assertEqual(["哥伦比娅"], self.client.page_requests)
        self.assertTrue(self.store.exists("pages", "哥伦比娅"))
        self.assertFalse(self.store.exists("pages", "阿蕾奇诺"))

    def test_probe_chronicle_category_returns_empty_when_no_category_matches(self) -> None:
        """测试 probe_chronicle_category 在站点无专用分类时返回空结果。"""
        result = self.crawler.probe_chronicle_category()

        self.assertEqual("", result["category_name"])
        self.assertEqual([], result["members"])
        self.assertEqual(["提瓦特", "公元", "编年"], self.client.category_requests)
        self.assertTrue(self.store.exists("chronicle_meta", "category_probe"))

    def test_crawl_chronicle_pages_falls_back_to_candidate_page_probe(self) -> None:
        """测试 crawl_chronicle_pages 在无分类时会回退到候选页面探测。"""
        result = self.crawler.crawl_chronicle_pages(page_limit=1)

        self.assertEqual("page", result["source_type"])
        self.assertEqual("", result["category_name"])
        self.assertEqual(["提瓦特编年史（公元纪）"], result["page_titles"])
        self.assertEqual(1, len(result["pages"]))
        self.assertEqual("提瓦特编年史（公元纪）", result["pages"][0]["title"])
        self.assertEqual(["提瓦特编年史（公元纪）", "提瓦特编年史（公元纪）"], self.client.page_requests)
        self.assertTrue(self.store.exists("pages", "提瓦特编年史（公元纪）"))
        self.assertTrue(self.store.exists("chronicle_meta", "page_probe"))


if __name__ == "__main__":
    unittest.main()
