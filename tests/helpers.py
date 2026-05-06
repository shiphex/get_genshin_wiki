"""
测试辅助工具模块
================

本模块提供测试所需的 mock 对象和辅助函数，
用于在不使用真实网络请求的情况下测试代码逻辑。

主要组件
--------
- build_page_payload() : 构建模拟的 MediaWiki API 页面响应
- FakeResponse         : 模拟 HTTP 响应对象
- FakeSession          : 模拟 requests.Session，按顺序返回预设响应

使用示例
--------
    from tests.helpers import build_page_payload, FakeResponse, FakeSession

    # 构建模拟页面 payload
    payload = build_page_payload("哥伦比娅", "{{角色}}")

    # 创建按顺序返回响应的 fake session
    session = FakeSession([FakeResponse({"query": {}}])
    client = MediaWikiClient(session=session)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests


def build_page_payload(title: str, wikitext: str, page_id: int = 1) -> dict[str, Any]:
    """
    构建模拟的 MediaWiki API 页面 payload。

    生成的 payload 格式与真实 MediaWiki API 响应一致，
    包含 query.pages 结构和一个修订版本。

    参数
    ----
    title : str
        页面标题
    wikitext : str
        页面 wikitext 内容
    page_id : int
        页面 ID，默认为 1

    返回
    ----
    dict[str, Any]
        模拟的 API 响应字典
    """
    return {
        "query": {
            "pages": {
                str(page_id): {
                    "pageid": page_id,
                    "title": title,
                    "revisions": [
                        {
                            "slots": {
                                "main": {
                                    "*": wikitext,
                                }
                            }
                        }
                    ],
                }
            }
        }
    }


@dataclass
class FakeResponse:
    """
    模拟 requests.Response 对象。

    用于 FakeSession 中，按预设值返回 JSON 数据或抛出异常。

    属性
    ----
    payload : Any
        要返回的 JSON 数据，或 Exception 对象（会被抛出）
    status_code : int
        HTTP 状态码，默认 200
    text : str | None
        响应文本，默认根据 payload 自动生成
    """

    payload: Any = None
    status_code: int = 200
    text: str | None = None

    def __post_init__(self) -> None:
        """如果 text 未提供，从 payload 自动生成。"""
        if self.text is None:
            self.text = json.dumps(self.payload, ensure_ascii=False)

    def json(self) -> Any:
        """
        返回 JSON 解析后的 payload。

        如果 payload 是 Exception，则抛出该异常。
        """
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    def raise_for_status(self) -> None:
        """如果状态码 >= 400，抛出 HTTPError。"""
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")


class FakeSession:
    """
    模拟 requests.Session 对象。

    按 FIFO（先进先出）顺序返回预设的响应列表，
    记录所有收到的请求以供验证。

    使用场景
    --------
    - 测试 API 请求参数是否正确
    - 模拟网络错误、超时等异常情况
    - 模拟分页响应
    """

    def __init__(self, responses: list[Any]) -> None:
        """
        初始化 FakeSession。

        参数
        ----
        responses : list[Any]
            要依次返回的响应列表，可以是 FakeResponse 或 Exception
        """
        self._responses = list(responses)  # 复制一份，避免修改原列表
        self.calls: list[dict[str, Any]] = []  # 记录所有收到的请求

    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float | None = None) -> Any:
        """
        模拟 GET 请求。

        记录请求参数并返回队列中的下一个响应。

        参数
        ----
        url : str
            请求 URL
        params : dict[str, Any] | None
            查询参数
        headers : dict[str, str] | None
            请求头
        timeout : float | None
            超时时间

        返回
        ----
        Any
            预设的响应对象

        异常
        ----
        AssertionError
            当响应队列为空时
        Exception
            当预设响应是 Exception 时
        """
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError("No fake responses remaining")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
