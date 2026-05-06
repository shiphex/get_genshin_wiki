"""
MediaWikiClient 单元测试
========================

测试 MediaWikiClient 的各项功能：
- robots.txt 访问权限检查
- 分类列表获取（支持分页）
- 分类成员获取（支持分页）
- 页面抓取
- 请求失败重试机制

测试方法
--------
- 使用 FakeSession 模拟 HTTP 响应
- 使用 FakeResponse 构建预设响应数据
- 模拟分页场景（返回 continue 参数）
"""

from __future__ import annotations

import unittest

import requests

from get_genshin_wiki.client import MediaWikiClient
from get_genshin_wiki.exceptions import PageContentNotFoundError, RobotsTxtDisallowedError
from get_genshin_wiki.models import RequestPolicy
from tests.helpers import FakeResponse, FakeSession, build_page_payload


class MediaWikiClientTests(unittest.TestCase):
    """MediaWikiClient 单元测试类。"""

    def make_client(self, responses: list[object]) -> MediaWikiClient:
        """
        创建配置了 FakeSession 的测试客户端。

        参数
        ----
        responses : list[object]
            FakeSession 要依次返回的响应列表

        返回
        ----
        MediaWikiClient
            配置好的测试客户端
        """
        return MediaWikiClient(
            session=FakeSession(responses),
            request_policy=RequestPolicy(
                user_agent="UnitTestBot",
                timeout_seconds=1.0,
                throttle_seconds=0.0,
                max_retries=1,
            ),
            sleep_func=lambda _: None,  # 禁用睡眠，加速测试
        )

    def test_assert_api_allowed_raises_when_robots_forbids_api(self) -> None:
        """
        测试 robots.txt 禁止访问时抛出异常。

        模拟 robots.txt 返回 "Disallow: /ys/api.php" 规则。
        """
        client = self.make_client([FakeResponse(text="User-agent: *\nDisallow: /ys/api.php\n")])

        with self.assertRaises(RobotsTxtDisallowedError):
            client.assert_api_allowed()

    def test_list_categories_collects_paginated_results(self) -> None:
        """
        测试分页分类列表的正确合并。

        模拟两次响应，分别返回部分分类和 continue 参数，
        验证最终结果包含所有分类。
        """
        client = self.make_client(
            [
                # 第一次响应：返回前两个分类，并指示还有更多
                FakeResponse(
                    {
                        "query": {"allcategories": [{"*": "角色"}, {"*": "武器"}]},
                        "continue": {"accontinue": "食物", "continue": "-||"},
                    }
                ),
                # 第二次响应：返回后续分类
                FakeResponse({"query": {"allcategories": [{"*": "食物"}]}}),
            ]
        )

        categories = client.list_categories()

        self.assertEqual(["角色", "武器", "食物"], categories)

    def test_list_category_members_collects_paginated_results(self) -> None:
        """
        测试分页分类成员列表的正确合并。
        """
        client = self.make_client(
            [
                FakeResponse(
                    {
                        "query": {"categorymembers": [{"title": "哥伦比娅"}]},
                        "continue": {"cmcontinue": "page|2", "continue": "-||"},
                    }
                ),
                FakeResponse({"query": {"categorymembers": [{"title": "阿蕾奇诺"}]}}),
            ]
        )

        members = client.list_category_members("角色")

        self.assertEqual(["哥伦比娅", "阿蕾奇诺"], members)

    def test_fetch_page_returns_wikitext(self) -> None:
        """
        测试 fetch_page 返回正确的页面数据。
        """
        client = self.make_client([FakeResponse(build_page_payload("哥伦比娅", "测试正文", page_id=99))])

        page = client.fetch_page("哥伦比娅")

        self.assertEqual("哥伦比娅", page.title)
        self.assertEqual(99, page.page_id)
        self.assertEqual("测试正文", page.wikitext)

    def test_fetch_page_raises_on_missing_revisions(self) -> None:
        """
        测试 fetch_page 在页面无修订历史时抛出异常。
        """
        client = self.make_client(
            [
                FakeResponse(
                    {
                        "query": {
                            "pages": {
                                "1": {"pageid": 1, "title": "哥伦比娅", "revisions": []}
                            }
                        }
                    }
                )
            ]
        )

        with self.assertRaises(PageContentNotFoundError):
            client.fetch_page("哥伦比娅")

    def test_request_retries_after_timeout(self) -> None:
        """
        测试请求超时时的自动重试机制。

        模拟第一次请求超时，第二次成功返回数据。
        """
        client = self.make_client(
            [
                requests.Timeout("boom"),  # 第一次超时
                FakeResponse({"query": {"allcategories": [{"*": "角色"}]}}),  # 重试成功
            ]
        )

        categories = client.list_categories()

        self.assertEqual(["角色"], categories)


if __name__ == "__main__":
    unittest.main()
