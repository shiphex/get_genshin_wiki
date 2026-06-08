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

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .client import MediaWikiClient
from .storage import JsonFileStore

_CHRONICLE_CATEGORY_CANDIDATES = (
    "提瓦特编年史",
    "提瓦特编年史（公元纪）",
    "公元纪",
)
_CHRONICLE_CATEGORY_PREFIXES = ("提瓦特", "公元", "编年")
_CHRONICLE_PAGE_CANDIDATES = (
    "提瓦特编年史（公元纪）",
    "提瓦特编年史",
    "编年史",
)
_CHRONICLE_META_NAMESPACE = "chronicle_meta"
_CHRONICLE_META_KEY = "category_probe"
_CHRONICLE_PAGE_META_KEY = "page_probe"


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

    def discover_character_quest_categories(self, persist: bool = True) -> dict[str, Any]:
        """
        探测角色传说任务与部族纪闻对应的实际 Wiki 分类名称。

        当前站点上「传说任务」与「部族纪闻」都存在独立分类，但实现上仍需
        以候选名和成员数量做一次实际探测，避免把概览页面误当成分类。
        """
        preferred_names = ("传说任务", "部族纪闻")
        prefixes = ("传说", "部族")
        ordered_candidates: list[str] = []
        seen: set[str] = set()

        def add_candidate(name: str) -> None:
            candidate = name.strip()
            if not candidate or candidate in seen:
                return
            seen.add(candidate)
            ordered_candidates.append(candidate)

        for name in preferred_names:
            add_candidate(name)
        for prefix in prefixes:
            for name in self.client.list_categories(prefix=prefix):
                if any(token in name for token in ("传说任务", "部族纪闻")):
                    add_candidate(name)

        category_map = {
            "传说任务": "",
            "部族纪闻": "",
        }
        probe_results: list[dict[str, Any]] = []
        for candidate in ordered_candidates:
            members = self.client.list_category_members(candidate)
            probe_results.append(
                {
                    "category_name": candidate,
                    "member_count": len(members),
                }
            )
            if len(members) <= 0:
                continue
            if "部族纪闻" in candidate and not category_map["部族纪闻"]:
                category_map["部族纪闻"] = candidate
                if persist:
                    self.store.write("category_members", candidate, members)
                continue
            if "传说任务" in candidate and not category_map["传说任务"]:
                category_map["传说任务"] = candidate
                if persist:
                    self.store.write("category_members", candidate, members)

        result = {
            "categories": [name for name in preferred_names if category_map[name]],
            "category_map": category_map,
            "probe_results": probe_results,
        }
        if persist:
            self.store.write("categories", "character-quests", result)
        return result

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

    def probe_north_library_category(self, prefix: str = "北陆图书馆") -> dict[str, Any]:
        """Probe the live wiki to find the canonical North Library category name."""
        candidates = self.client.list_categories(prefix=prefix)
        category_name = next((item for item in candidates if item == prefix), "")
        if not category_name and candidates:
            category_name = sorted(candidates, key=lambda item: (len(item), item))[0]
        return {
            "category_name": category_name or prefix,
            "category_candidates": candidates,
        }

    def crawl_north_library(
        self,
        title: str = "北陆图书馆",
        persist: bool = True,
    ) -> dict[str, Any]:
        """Fetch the North Library page payload and its discovered category metadata."""
        payload = self.crawl_page(title, persist=persist)
        page = next(iter(payload.get("query", {}).get("pages", {}).values()), {})
        probe = self.probe_north_library_category(prefix=title)
        return {
            "title": page.get("title", title),
            "page_id": page.get("pageid"),
            "category_name": probe["category_name"],
            "category_candidates": probe["category_candidates"],
            "payload": payload,
        }

    def probe_chronicle_category(
        self,
        *,
        candidates: Sequence[str] = _CHRONICLE_CATEGORY_CANDIDATES,
        prefixes: Sequence[str] = _CHRONICLE_CATEGORY_PREFIXES,
        persist: bool = True,
    ) -> dict[str, Any]:
        """
        探测提瓦特编年史对应的真实分类名称。

        先根据候选名和前缀收集可能的分类，再逐个探测其成员，
        选择第一个存在且拥有成员页面的分类。
        """
        ordered_candidates: list[str] = []
        seen: set[str] = set()

        def add_candidate(name: str) -> None:
            candidate = name.strip()
            if not candidate or candidate in seen:
                return
            seen.add(candidate)
            ordered_candidates.append(candidate)

        for name in candidates:
            add_candidate(name)

        discovered: list[str] = []
        for prefix in prefixes:
            for category_name in self.client.list_categories(prefix=prefix):
                if self._score_chronicle_category(category_name, candidates) <= 0:
                    continue
                discovered.append(category_name)

        for category_name in sorted(
            set(discovered),
            key=lambda item: (-self._score_chronicle_category(item, candidates), item),
        ):
            add_candidate(category_name)

        probe_results: list[dict[str, Any]] = []
        detected_name = ""
        detected_members: list[str] = []
        for category_name in ordered_candidates:
            members = self.client.list_category_members(category_name)
            member_count = len(members)
            probe_results.append(
                {
                    "category_name": category_name,
                    "member_count": member_count,
                }
            )
            if member_count <= 0 or detected_name:
                continue
            detected_name = category_name
            detected_members = members
            if persist:
                self.store.write("category_members", category_name, members)
            break

        result = {
            "category_name": detected_name,
            "members": detected_members,
            "probe_results": probe_results,
        }
        if persist:
            self.store.write(_CHRONICLE_META_NAMESPACE, _CHRONICLE_META_KEY, result)
        return result

    def crawl_chronicle_pages(
        self,
        page_limit: int | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """
        探测并抓取提瓦特编年史分类下的全部页面。

        返回探测出的分类名以及抓取结果；若分类不存在则显式报错。
        """
        probe_result = self.probe_chronicle_category(persist=persist)
        category_name = probe_result["category_name"]
        source_type = "category"
        members = list(probe_result["members"])
        page_probe_result: dict[str, Any] | None = None

        if not category_name:
            source_type = "page"
            page_probe_result = self.probe_chronicle_pages_by_title(persist=persist)
            members = list(page_probe_result["titles"])
            if not members:
                raise ValueError("could not detect a chronicle category or fallback chronicle pages")

        if page_limit is not None:
            members = members[:page_limit]

        pages: list[dict[str, Any]] = []
        for title in members:
            payload = self.client.fetch_page_payload(title)
            page_result = self._page_metadata(payload, fallback_title=title)
            if persist:
                page_result["path"] = self.store.write("pages", title, payload)
            pages.append(page_result)

        return {
            "source_type": source_type,
            "category_name": category_name,
            "page_titles": [] if page_probe_result is None else page_probe_result["titles"],
            "pages": pages,
        }

    def probe_chronicle_pages_by_title(
        self,
        *,
        candidates: Sequence[str] = _CHRONICLE_PAGE_CANDIDATES,
        persist: bool = True,
    ) -> dict[str, Any]:
        """
        在缺少专用分类时，按候选页面标题探测编年史页面。

        优先使用显式的「提瓦特编年史（公元纪）」页面，跳过重定向页。
        """
        titles: list[str] = []
        probe_results: list[dict[str, Any]] = []
        for title in candidates:
            payload = self.client.fetch_page_payload(title)
            page = next(iter(payload.get("query", {}).get("pages", {}).values()), {})
            actual_title = str(page.get("title", title))
            wikitext = self._extract_page_wikitext(payload)
            has_wikitext = bool(wikitext.strip())
            is_redirect = self._is_redirect_wikitext(wikitext)
            looks_like_chronicle = self._looks_like_chronicle_wikitext(wikitext)
            probe_results.append(
                {
                    "requested_title": title,
                    "actual_title": actual_title,
                    "has_wikitext": has_wikitext,
                    "is_redirect": is_redirect,
                    "looks_like_chronicle": looks_like_chronicle,
                }
            )
            if not has_wikitext or is_redirect or not looks_like_chronicle:
                continue
            titles.append(actual_title)
            if persist:
                self.store.write("pages", actual_title, payload)
            break

        result = {
            "titles": titles,
            "probe_results": probe_results,
        }
        if persist:
            self.store.write(_CHRONICLE_META_NAMESPACE, _CHRONICLE_PAGE_META_KEY, result)
        return result

    def _page_metadata(self, payload: dict[str, Any], *, fallback_title: str) -> dict[str, Any]:
        """从页面 payload 中提取稳定的标题与 page_id。"""
        pages = payload.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        return {
            "title": page.get("title", fallback_title),
            "page_id": page.get("pageid"),
        }

    def _score_chronicle_category(self, category_name: str, candidates: Sequence[str]) -> int:
        """为编年史分类候选项打分，优先 exact match，再匹配核心关键词。"""
        if category_name in candidates:
            return 100

        score = 0
        for candidate in candidates:
            if candidate in category_name or category_name in candidate:
                score += 25
        for keyword in ("提瓦特", "编年", "公元纪"):
            if keyword in category_name:
                score += 10
        return score

    def _extract_page_wikitext(self, payload: dict[str, Any]) -> str:
        """从页面 payload 中提取主插槽 wikitext。"""
        pages = payload.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        revisions = page.get("revisions", [])
        if not revisions:
            return ""
        return revisions[0].get("slots", {}).get("main", {}).get("*", "")

    def _is_redirect_wikitext(self, wikitext: str) -> bool:
        """判断页面是否仅为重定向。"""
        normalized = wikitext.lstrip().lower()
        return normalized.startswith("#重定向") or normalized.startswith("#redirect")

    def _looks_like_chronicle_wikitext(self, wikitext: str) -> bool:
        """判断页面正文是否像编年史/公元纪条目。"""
        if not wikitext.strip():
            return False
        if "公元纪年" in wikitext:
            return True
        if "编年史" in wikitext and ("===" in wikitext or "'''" in wikitext):
            return True
        return False
