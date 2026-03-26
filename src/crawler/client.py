"""MediaWiki API 客户端"""
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class MediaWikiError(Exception):
    """MediaWiki API 错误"""
    def __init__(self, code: str, info: str):
        self.code = code
        self.info = info
        super().__init__(f"MediaWiki API Error [{code}]: {info}")


class MediaWikiClient:
    """MediaWiki API 客户端"""

    def __init__(
        self,
        api_url: str = "https://wiki.biligame.com/ys/api.php",
        base_url: str = "https://wiki.biligame.com/ys/",
        request_interval: float = 5.0,
        timeout: int = 30,
        max_retries: int = 3,
        user_agent: str = "get_wiki_genshin/0.1.0",
    ):
        self.api_url = api_url
        self.base_url = base_url
        self.request_interval = request_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Accept-Language": "zh-CN",
            "Referer": base_url,
        })
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}

        self._last_request_time = 0.0

    def _wait_interval(self) -> None:
        """等待请求间隔"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self._last_request_time = time.time()

    def _request(self, method: str, params: dict) -> dict:
        """发送 API 请求"""
        self._wait_interval()

        for retry in range(self.max_retries):
            try:
                response = self.session.request(
                    method,
                    self.api_url,
                    params=params,
                    timeout=self.timeout,
                )
                response.raise_for_status()

                data = response.json()
                if "error" in data:
                    raise MediaWikiError(
                        code=data["error"].get("code", "unknown"),
                        info=data["error"].get("info", "unknown error"),
                    )
                return data

            except requests.exceptions.Timeout:
                logger.warning(f"请求超时，重试 ({retry + 1}/{self.max_retries})")
                if retry < self.max_retries - 1:
                    time.sleep(2 ** retry * 5)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.warning(f"429 限速，重试 ({retry + 1}/{self.max_retries})")
                    if retry < self.max_retries - 1:
                        time.sleep(2 ** retry * 5)
                elif 500 <= e.response.status_code < 600:
                    logger.warning(f"服务器错误 {e.response.status_code}，重试 ({retry + 1}/{self.max_retries})")
                    if retry < self.max_retries - 1:
                        time.sleep(2 ** retry * 5)
                else:
                    raise
            except requests.exceptions.RequestException as e:
                logger.warning(f"请求异常: {e}，重试 ({retry + 1}/{self.max_retries})")
                if retry < self.max_retries - 1:
                    time.sleep(2 ** retry * 5)

        raise MediaWikiError("max_retries", f"达到最大重试次数 {self.max_retries}")

    def get_page_html(self, title: str) -> str:
        """获取页面渲染后的 HTML

        Args:
            title: 页面标题

        Returns:
            渲染后的 HTML 内容
        """
        params = {
            "action": "parse",
            "page": title,
            "format": "json",
            "prop": "text",
        }
        data = self._request("GET", params)
        return data["parse"]["text"]["*"]

    def get_page_info(self, title: str) -> dict:
        """获取页面基本信息

        Args:
            title: 页面标题

        Returns:
            页面信息字典
        """
        params = {
            "action": "query",
            "titles": title,
            "format": "json",
            "prop": "info",
            "inprop": "url|displaytitle",
        }
        data = self._request("GET", params)
        pages = data["query"]["pages"]
        return next(iter(pages.values()))

    def get_page_text(self, title: str) -> str:
        """获取页面纯文本（wikitext）

        Args:
            title: 页面标题

        Returns:
            页面的 wikitext
        """
        params = {
            "action": "query",
            "titles": title,
            "format": "json",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
        }
        data = self._request("GET", params)
        pages = data["query"]["pages"]
        page = next(iter(pages.values()))
        revisions = page.get("revisions", [])
        if revisions:
            return revisions[0]["slots"]["main"]["*"]
        return ""
