"""
项目自定义异常定义
==================

本模块定义了项目中可能出现的各类异常类型，便于调用方进行统一的异常捕获与处理。

异常层次结构
------------
GetGenshinWikiError (基类)
├── RobotsTxtDisallowedError  - robots.txt 禁止访问
├── MediaWikiRequestError     - API 请求失败
├── PageContentNotFoundError  - 页面内容不存在
└── ParsingError              - 解析失败

使用示例
--------
    from get_genshin_wiki.exceptions import RobotsTxtDisallowedError

    try:
        client.assert_api_allowed()
    except RobotsTxtDisallowedError as e:
        print(f"访问被禁止: {e}")
"""


# 异常基类，所有项目自定义异常的父类
class GetGenshinWikiError(Exception):
    """
    项目异常基类。

    当需要捕获本项目的任何异常时，可直接使用此基类。
    """

    pass


# robots.txt 访问被拒绝异常
class RobotsTxtDisallowedError(GetGenshinWikiError):
    """
    当 robots.txt 规则禁止访问目标路径时抛出。

    通常在调用 MediaWikiClient.assert_api_allowed() 方法检查 API 可访问性时触发。
    """

    pass


# MediaWiki API 请求异常
class MediaWikiRequestError(GetGenshinWikiError):
    """
    当 MediaWiki API 请求失败时抛出。

    可能的原因包括：
    - 网络连接问题
    - API 返回错误响应
    - 超过最大重试次数
    """

    pass


# 页面内容未找到异常
class PageContentNotFoundError(GetGenshinWikiError):
    """
    当获取到的页面数据中不包含预期的修订内容时抛出。

    可能的情况：
    - 页面不存在（已删除或标题错误）
    - 页面无修订历史
    - wikitext 内容为空
    """

    pass


# 解析异常
class ParsingError(GetGenshinWikiError):
    """
    当无法将 MediaWiki 页面内容解析为结构化数据时抛出。

    可能的原因：
    - 页面 payload 格式不符合预期
    - 缺少必要的字段（如 query.pages）
    - wikitext 为空或格式异常
    """

    pass
