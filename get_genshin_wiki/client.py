"""
MediaWiki API 客户端
====================

本模块封装了与 MediaWiki API 的交互逻辑，提供：
- 分类列表获取
- 分类成员列表获取
- 单个页面内容抓取
- robots.txt 访问权限检查
- 请求限流与自动重试

设计特点
--------
- 可测试性：通过注入 session、sleep_func、now_func 等依赖，便于单元测试
- 限流：自动在请求间插入延迟，遵守站点访问频率限制
- 重试：网络错误时自动重试（最多 max_retries 次）
- 分页：自动处理 MediaWiki API 的分页请求

使用示例
--------
    from get_genshin_wiki.client import MediaWikiClient

    client = MediaWikiClient()
    client.assert_api_allowed()  # 检查 robots.txt
    categories = client.list_categories(prefix="角色")
    members = client.list_category_members("角色")
    page = client.fetch_page("哥伦比娅")
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .config import API_URL, MAX_RETRIES, REQUEST_THROTTLE_SECONDS, REQUEST_TIMEOUT_SECONDS, USER_AGENT
from .exceptions import MediaWikiRequestError, PageContentNotFoundError, RobotsTxtDisallowedError
from .models import RequestPolicy, WikiPage


class MediaWikiClient:
    """
    MediaWiki API 客户端封装类。

    提供与 MediaWiki API 通信的轻量级、可测试的接口。
    支持分类查询、页面抓取、请求限流、失败重试等核心功能。

    属性
    ----
    api_url : str
        MediaWiki API 端点地址
    request_policy : RequestPolicy
        HTTP 请求策略配置
    session : requests.Session
        HTTP 会话对象
    """

    def __init__(
        self,
        api_url: str = API_URL,
        request_policy: RequestPolicy | None = None,
        session: requests.Session | None = None,
        sleep_func: Callable[[float], None] | None = None,
        now_func: Callable[[], float] | None = None,
    ) -> None:
        self.api_url = api_url
        # 使用提供的请求策略或创建默认策略
        self.request_policy = request_policy or RequestPolicy(
            user_agent=USER_AGENT,
            timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            throttle_seconds=REQUEST_THROTTLE_SECONDS,
            max_retries=MAX_RETRIES,
        )
        # HTTP 会话：使用提供的或创建新的
        self.session = session or requests.Session()
        # 睡眠函数：用于测试时注入 mock 函数
        self.sleep = sleep_func or time.sleep
        # 时间函数：用于测试时注入 mock 函数
        self.now = now_func or time.monotonic
        # 记录上次请求时间，用于限流计算
        self._last_request_at: float | None = None
        # robots.txt 解析器缓存
        self._robots_parser: RobotFileParser | None = None

    @property
    def site_root(self) -> str:
        """
        从 API URL 中提取站点根地址。

        例如：https://wiki.biligame.com/ys/api.php -> https://wiki.biligame.com
        """
        parts = urlsplit(self.api_url)
        return f"{parts.scheme}://{parts.netloc}"

    def _headers(self) -> dict[str, str]:
        """
        构建 HTTP 请求头。

        返回包含 Accept、Referer、User-Agent 的字典。
        """
        return {
            "Accept": "application/json",
            "Referer": f"{self.site_root}/ys/",
            "User-Agent": self.request_policy.user_agent,
        }

    def load_robots_parser(self) -> RobotFileParser:
        """
        加载并解析 robots.txt 文件。

        从站点根目录获取 robots.txt，解析后缓存解析结果。

        返回
        ----
        RobotFileParser
            解析后的 robots.txt 解析器对象
        """
        robots_url = f"{self.site_root}/robots.txt"
        response = self.session.get(
            robots_url,
            headers=self._headers(),
            timeout=self.request_policy.timeout_seconds,
        )
        response.raise_for_status()
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        self._robots_parser = parser
        return parser

    def assert_api_allowed(self) -> None:
        """
        检查 API 是否允许访问。

        根据 robots.txt 规则判断是否可以访问 API。
        如不允许，抛出 RobotsTxtDisallowedError 异常。

        异常
        ----
        RobotsTxtDisallowedError
            当 robots.txt 禁止访问 API 时抛出
        """
        parser = self._robots_parser or self.load_robots_parser()
        if not parser.can_fetch(self.request_policy.user_agent, self.api_url):
            raise RobotsTxtDisallowedError(f"robots.txt disallows {self.api_url}")

    def _apply_throttle(self) -> None:
        """
        应用请求限流。

        根据上次请求时间计算需要等待的时长，
        如果距上次请求时间不足 throttle_seconds，则等待相应时长。
        """
        if self._last_request_at is None:
            return
        elapsed = self.now() - self._last_request_at
        wait_for = self.request_policy.throttle_seconds - elapsed
        if wait_for > 0:
            self.sleep(wait_for)

    def _request(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """
        执行 HTTP GET 请求到 MediaWiki API。

        内部自动处理限流、重试和错误处理。

        参数
        ----
        params : Mapping[str, Any]
            API 查询参数字典

        返回
        ----
        dict[str, Any]
            API 返回的 JSON 响应

        异常
        ----
        MediaWikiRequestError
            当请求失败且达到最大重试次数时抛出
        """
        last_error: Exception | None = None
        for attempt in range(self.request_policy.max_retries + 1):
            try:
                # 应用限流
                self._apply_throttle()
                # 发送请求
                response = self.session.get(
                    self.api_url,
                    params=params,
                    headers=self._headers(),
                    timeout=self.request_policy.timeout_seconds,
                )
                self._last_request_at = self.now()
                response.raise_for_status()
                payload = response.json()
                # 验证响应格式
                if not isinstance(payload, dict):
                    raise MediaWikiRequestError("MediaWiki payload is not a JSON object")
                return payload
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt >= self.request_policy.max_retries:
                    break
                # 指数退避重试：0.5s, 1s, 2s...
                self.sleep(min(2.0, 0.5 * (attempt + 1)))
        raise MediaWikiRequestError("MediaWiki request failed") from last_error

    def _collect_paginated(
        self,
        params: Mapping[str, Any],
        collection_key: tuple[str, str],
        item_key: str,
    ) -> list[Any]:
        """
        递归获取分页查询的全部结果。

        MediaWiki API 对大量结果返回分页，需要多次请求并合并。

        参数
        ----
        params : Mapping[str, Any]
            初始查询参数
        collection_key : tuple[str, str]
            JSON 响应中结果数组的路径，如 ("query", "allcategories")
        item_key : str
            每条结果中要提取的字段名

        返回
        ----
        list[Any]
            所有分页结果的合并列表
        """
        items: list[Any] = []
        next_params = dict(params)
        while True:
            payload = self._request(next_params)
            # 从嵌套字典中提取数据列表
            data = payload.get(collection_key[0], {}).get(collection_key[1], [])
            for item in data:
                if item_key in item:
                    items.append(item[item_key])
            # 检查是否还有后续分页
            continuation = payload.get("continue")
            if not continuation:
                return items
            # 更新查询参数以获取下一页
            next_params.update(continuation)

    def list_categories(self, prefix: str | None = None) -> list[str]:
        """
        获取 Wiki 分类列表。

        参数
        ----
        prefix : str | None
            可选的分类名前缀过滤，只返回以此开头的分类

        返回
        ----
        list[str]
            分类名称列表

        示例
        ----
            client.list_categories()           # 返回所有分类
            client.list_categories("角色")      # 返回以"角色"开头的分类
        """
        params: dict[str, Any] = {
            "action": "query",
            "list": "allcategories",
            "aclimit": "max",  # 请求最大数量
            "format": "json",
        }
        if prefix:
            params["acprefix"] = prefix
        return self._collect_paginated(params, ("query", "allcategories"), "*")

    def list_category_members(self, category_name: str) -> list[str]:
        """
        获取指定分类下的成员页面列表。

        参数
        ----
        category_name : str
            分类名称（不含 "Category:" 前缀）

        返回
        ----
        list[str]
            分类中的页面标题列表

        示例
        ----
            client.list_category_members("角色")  # 获取所有角色页面
        """
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category_name}",
            "cmlimit": "max",
            "format": "json",
        }
        return self._collect_paginated(params, ("query", "categorymembers"), "title")

    def fetch_page_payload(self, title: str) -> dict[str, Any]:
        """
        获取指定页面的原始 API 响应（payload）。

        返回完整的 API JSON 响应，包含页面元数据和修订历史。

        参数
        ----
        title : str
            页面标题

        返回
        ----
        dict[str, Any]
            MediaWiki API 的原始 JSON 响应
        """
        params = {
            "action": "query",
            "prop": "revisions|categories",
            "titles": title,
            "rvprop": "content",  # 获取 wikitext 内容
            "rvslots": "main",    # 获取主插槽内容
            "cllimit": "max",
            "format": "json",
        }
        return self._request(params)

    def fetch_rendered_section_titles(self, title: str) -> list[str]:
        """
        获取页面渲染后的章节标题列表。

        使用 MediaWiki parse API 读取渲染后的 section 信息，
        以便处理由模板展开生成的章节结构。
        """
        payload = self._request(
            {
                "action": "parse",
                "page": title,
                "prop": "sections",
                "format": "json",
            }
        )
        sections = payload.get("parse", {}).get("sections", [])
        titles: list[str] = []
        for section in sections:
            line = section.get("line", "")
            if isinstance(line, str) and line.strip():
                titles.append(line.strip())
        return titles

    def fetch_page(self, title: str) -> WikiPage:
        """
        获取指定页面的结构化数据。

        自动处理响应解析，提取 wikitext 和元数据。

        参数
        ----
        title : str
            页面标题

        返回
        ----
        WikiPage
            包含页面标题、ID、wikitext 和原始 payload 的对象

        异常
        ----
        PageContentNotFoundError
            当页面不存在、无修订历史或 wikitext 为空时抛出
        """
        payload = self.fetch_page_payload(title)
        pages = payload.get("query", {}).get("pages", {})
        if not pages:
            raise PageContentNotFoundError(f"page payload has no pages for {title}")
        page = next(iter(pages.values()))
        revisions = page.get("revisions", [])
        if not revisions:
            raise PageContentNotFoundError(f"page {title} has no revisions")
        slots = revisions[0].get("slots", {})
        main_slot = slots.get("main", {})
        wikitext = main_slot.get("*", "")
        if not wikitext:
            raise PageContentNotFoundError(f"page {title} has empty wikitext")
        return WikiPage(
            title=page.get("title", title),
            page_id=page.get("pageid"),
            wikitext=wikitext,
            raw_payload=payload,
        )
