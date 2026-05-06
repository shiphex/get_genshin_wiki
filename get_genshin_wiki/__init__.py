"""
get_genshin_wiki - 原神 Wiki 数据抓取与解析工具包
=================================================

本包提供从 Genshin Impact (原神) Wiki 网站抓取页面数据、解析 WikiText 内容、
并持久化存储到本地 JSON 文件的功能。

主要模块
--------
- client   : MediaWiki API 客户端，负责与 Wiki API 通信
- crawler  : 爬虫编排层，协调客户端抓取与存储持久化
- parser   : WikiText 解析器，将原始 wikitext 转换为结构化数据
- storage  : JSON 文件存储管理器

使用示例
--------
    from get_genshin_wiki import MediaWikiClient, WikiCrawler, JsonFileStore

    store = JsonFileStore()
    client = MediaWikiClient()
    crawler = WikiCrawler(client=client, store=store)

    # 抓取角色分类
    categories = crawler.crawl_categories(prefix="角色")
"""

from .client import MediaWikiClient
from .crawler import WikiCrawler
from .parser import WikiTextParser
from .storage import JsonFileStore

# 包的公共接口，供外部 from get_genshin_wiki import xxx 使用
__all__ = [
    "JsonFileStore",
    "MediaWikiClient",
    "WikiCrawler",
    "WikiTextParser",
]
