"""
爬虫编排层
==========

本模块协调远程数据抓取与本地 JSON 持久化存储。

WikiCrawler 类作为门面（Facade），封装了：
- 客户端（MediaWikiClient）负责网络请求
- 存储（JsonFileStore）负责数据持久化

设计目的
--------
将"抓取逻辑"与"存储逻辑"分离，使爬虫可以灵活选择：
- 是否持久化数据（persist 参数）
- 限制抓取数量（page_limit 参数）

使用示例
--------
    from get_genshin_wiki import MediaWikiClient, WikiCrawler, JsonFileStore

    store = JsonFileStore()
    client = MediaWikiClient()
    crawler = WikiCrawler(client=client, store=store)

    # 抓取分类（自动持久化）
    categories = crawler.crawl_categories()

    # 抓取分类成员
    members = crawler.crawl_category_members("角色")

    # 抓取整个分类的所有页面
    paths = crawler.crawl_category_pages("角色", page_limit=10)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import MediaWikiClient
from .storage import JsonFileStore


class WikiCrawler:
    """
    Wiki 数据爬虫编排器。

    协调 MediaWikiClient 和 JsonFileStore，实现：
    - 分类列表抓取
    - 分类成员抓取
    - 单页面抓取
    - 批量分类页面抓取

    所有方法都支持可选的持久化（默认开启）。
    """

    def __init__(self, client: MediaWikiClient, store: JsonFileStore) -> None:
        """
        初始化爬虫编排器。

        参数
        ----
        client : MediaWikiClient
            MediaWiki API 客户端实例
        store : JsonFileStore
            JSON 文件存储实例
        """
        self.client = client
        self.store = store

    def crawl_categories(self, prefix: str | None = None, persist: bool = True) -> list[str]:
        """
        抓取 Wiki 分类列表。

        参数
        ----
        prefix : str | None
            可选的分类名前缀过滤
        persist : bool
            是否持久化到本地存储，默认为 True

        返回
        ----
        list[str]
            分类名称列表
        """
        categories = self.client.list_categories(prefix=prefix)
        if persist:
            # 存储键名格式：categories::前缀 或 categories::all
            key = f"categories::{prefix or 'all'}"
            self.store.write("categories", key, categories)
        return categories

    def discover_event_quest_category(self, persist: bool = True) -> str:
        """
        探测活动任务所属的实际 Wiki 分类名称。

        当前站点上活动任务成员页位于“活动事件”分类，而“活动任务”是概览页面。
        """
        categories = self.client.list_categories(prefix="活动")
        preferred_names = ("活动事件", "活动任务")
        category_name = next((name for name in preferred_names if name in categories), "")
        if not category_name:
            for name in categories:
                if "活动" in name and ("事件" in name or "任务" in name):
                    category_name = name
                    break
        if not category_name:
            raise ValueError("Unable to discover event quest category from wiki categories")
        if persist:
            self.store.write("categories", "event-quests", {"category": category_name})
        return category_name

    def crawl_category_members(self, category_name: str, persist: bool = True) -> list[str]:
        """
        抓取指定分类下的成员页面列表。

        参数
        ----
        category_name : str
            分类名称
        persist : bool
            是否持久化到本地存储，默认为 True

        返回
        ----
        list[str]
            分类成员标题列表
        """
        members = self.client.list_category_members(category_name)
        if persist:
            self.store.write("category_members", category_name, members)
        return members

    def crawl_page(self, title: str, persist: bool = True) -> dict[str, Any]:
        """
        抓取单个页面的完整 payload。

        参数
        ----
        title : str
            页面标题
        persist : bool
            是否持久化到本地存储，默认为 True

        返回
        ----
        dict[str, Any]
            MediaWiki API 原始响应 payload
        """
        payload = self.client.fetch_page_payload(title)
        if persist:
            self.store.write("pages", title, payload)
        return payload

    def crawl_category_pages(
        self,
        category_name: str,
        page_limit: int | None = None,
        persist: bool = True,
    ) -> list[Path]:
        """
        批量抓取指定分类下所有成员页面。

        依次获取分类成员列表，然后逐个抓取页面内容。

        参数
        ----
        category_name : str
            分类名称
        page_limit : int | None
            可选的抓取数量限制，默认为 None（抓取全部）
        persist : bool
            是否持久化到本地存储，默认为 True

        返回
        ----
        list[Path]
            已保存的页面文件路径列表
        """
        members = self.crawl_category_members(category_name, persist=persist)
        # 应用数量限制
        if page_limit is not None:
            members = members[:page_limit]
        written_paths: list[Path] = []
        for title in members:
            payload = self.client.fetch_page_payload(title)
            if persist:
                written_paths.append(self.store.write("pages", title, payload))
        return written_paths
