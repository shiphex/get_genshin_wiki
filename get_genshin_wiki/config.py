"""
项目配置默认值
==============

本模块定义了连接 Genshin Impact Wiki (biligame) 所需的默认配置参数，
包括 API 地址、HTTP 请求策略、数据存储路径等。

配置项说明
----------
- API_URL               : MediaWiki API 端点地址
- USER_AGENT            : HTTP 请求头中的 User-Agent，需遵循各站点的 robots.txt 规则
- REQUEST_TIMEOUT_SECONDS : 单次 HTTP 请求的超时时间（秒）
- REQUEST_THROTTLE_SECONDS : 两次请求之间的最小间隔（秒），用于遵守站点访问频率限制
- MAX_RETRIES           : 请求失败时的最大重试次数
- DATA_ROOT             : 本地 JSON 数据存储的根目录

注意事项
--------
这些默认值可通过 MediaWikiClient 和 JsonFileStore 的构造函数进行覆盖。
建议在生产环境中根据实际需求调整 REQUEST_THROTTLE_SECONDS 以避免对目标站点造成压力。
"""

from __future__ import annotations

from pathlib import Path

# MediaWiki API 端点 - 指向 BiliGame 原神 Wiki
API_URL = "https://wiki.biligame.com/ys/api.php"

# HTTP User-Agent 头信息，需包含项目主页或联系邮箱
# 良好的 User-Agent 有助于站点管理员识别请求来源
USER_AGENT = "get-genshin-wiki/0.1 (+https://wiki.biligame.com/ys/)"

# HTTP 请求超时时间（秒）
REQUEST_TIMEOUT_SECONDS = 15.0

# 请求限流：两次 API 请求之间的最小间隔（秒）
# 默认 1 秒，遵守目标站点的 robots.txt 访问频率限制
REQUEST_THROTTLE_SECONDS = 1.0

# 网络请求失败时的最大重试次数
MAX_RETRIES = 2

# 本地 JSON 数据存储的根目录路径
# 所有通过 JsonFileStore 存储的文件都将放在此目录下
DATA_ROOT = Path("data")
