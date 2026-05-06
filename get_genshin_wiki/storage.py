"""
JSON 文件存储管理器
==================

本模块提供基于文件系统的 JSON 数据持久化存储功能。

核心特性
--------
- 命名空间隔离：不同类型的数据存储在不同目录下
- 文件名安全：使用哈希处理后的文件名，避免文件系统特殊字符问题
- 原子写入：直接写入文件，简单可靠
- 增量更新：支持 update（合并）和 add（追加）操作

存储结构
--------
    data_root/
    ├── categories/       # 分类列表
    │   └── categories__a1b2c3.json
    ├── category_members/ # 分类成员
    │   └── 角色__d4e5f6.json
    ├── pages/           # 原始页面 payload
    │   └── 哥伦比娅__g7h8i9.json
    └── parsed/          # 解析后的数据
        ├── pages/
        └── characters/

使用示例
--------
    from get_genshin_wiki.storage import JsonFileStore

    store = JsonFileStore(Path("data"))

    # 基本读写
    store.write("characters", "哥伦比娅", {"element": "冰"})
    data = store.read("characters", "哥伦比娅")

    # 增量更新（合并字典）
    store.update("characters", "哥伦比娅", {"weapon": "法器"})

    # 追加到列表
    store.add("pages", "visited", ["哥伦比娅"])
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import DATA_ROOT

# 文件名禁用字符正则：< > : " / \ | ? *
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]+')


class JsonFileStore:
    """
    JSON 文件存储管理器。

    将数据以 JSON 格式存储在文件系统中，按命名空间分目录管理。
    支持基本的 CRUD 操作以及增量更新（merge/add）。

    属性
    ----
    root : Path
        存储根目录
    """

    def __init__(self, root: Path | None = None) -> None:
        """
        初始化存储管理器。

        参数
        ----
        root : Path | None
            存储根目录，默认为 config.DATA_ROOT (data/)
        """
        self.root = Path(root or DATA_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    def namespace_dir(self, namespace: str) -> Path:
        """
        获取命名空间目录路径，不存在则创建。

        参数
        ----
        namespace : str
            命名空间名称（如 "pages"、"characters"）

        返回
        ----
        Path
            命名空间目录的 Path 对象
        """
        path = self.root / namespace
        path.mkdir(parents=True, exist_ok=True)
        return path

    def build_filename(self, key: str) -> str:
        """
        为给定的键构建安全的文件名。

        处理逻辑：
        1. 将 key 中的非法字符替换为下划线
        2. 如果结果为空，则使用 "item"
        3. 在末尾添加 key 的 SHA1 哈希前 10 位，保证唯一性

        参数
        ----
        key : str
            数据键名

        返回
        ----
        str
            安全的文件名，格式：{normalized_key}__{hash}.json
        """
        # 替换非法字符并去除首尾空白和点
        normalized = _INVALID_FILENAME_CHARS.sub("_", key).strip().strip(".")
        if not normalized:
            normalized = "item"
        # 添加哈希前缀保证唯一性，即使不同 key 规范化后相同也能区分
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
        return f"{normalized}__{digest}.json"

    def resolve_path(self, namespace: str, key: str) -> Path:
        """
        解析数据项的完整文件路径。

        参数
        ----
        namespace : str
            命名空间
        key : str
            数据键名

        返回
        ----
        Path
            完整文件路径
        """
        return self.namespace_dir(namespace) / self.build_filename(key)

    def write(self, namespace: str, key: str, payload: Any) -> Path:
        """
        将数据写入存储（覆盖或新建）。

        参数
        ----
        namespace : str
            命名空间
        key : str
            数据键名
        payload : Any
            要存储的数据（必须为 JSON 可序列化类型）

        返回
        ----
        Path
            保存文件的路径
        """
        path = self.resolve_path(namespace, key)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return path

    def read(self, namespace: str, key: str) -> Any:
        """
        从存储中读取数据。

        参数
        ----
        namespace : str
            命名空间
        key : str
            数据键名

        返回
        ----
        Any
            读取的数据
        """
        path = self.resolve_path(namespace, key)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def update(self, namespace: str, key: str, payload: dict[str, Any]) -> Any:
        """
        合并更新存储中的字典数据。

        将新 payload 与已存储的数据合并（浅合并），
        新值会覆盖已存在的同名键。

        参数
        ----
        namespace : str
            命名空间
        key : str
            数据键名
        payload : dict[str, Any]
            要合并的字典数据

        返回
        ----
        Any
            合并后的完整数据

        异常
        ----
        TypeError
            当存储的数据或 payload 不是字典时抛出
        """
        current = self.read(namespace, key)
        if not isinstance(current, dict):
            raise TypeError("update requires the stored payload to be a JSON object")
        if not isinstance(payload, dict):
            raise TypeError("update payload must be a JSON object")
        updated = dict(current)
        updated.update(payload)
        self.write(namespace, key, updated)
        return updated

    def add(self, namespace: str, key: str, payload: Any) -> Any:
        """
        向存储中的数据追加内容。

        支持两种追加模式：
        - 存储的是列表：则追加到列表（支持列表或单个元素）
        - 存储的是字典：则向字典添加新键值对（不允许覆盖已有键）

        参数
        ----
        namespace : str
            命名空间
        key : str
            数据键名
        payload : Any
            要追加的内容

        返回
        ----
        Any
            追加后的完整数据

        异常
        ----
        TypeError
            当存储类型不支持追加操作时抛出
        ValueError
            当添加的字典包含已存在的键时抛出
        """
        current = self.read(namespace, key)
        # 列表：追加模式
        if isinstance(current, list):
            updated = list(current)
            if isinstance(payload, list):
                updated.extend(payload)
            else:
                updated.append(payload)
            self.write(namespace, key, updated)
            return updated
        # 字典：检查冲突后添加新键
        if isinstance(current, dict):
            if not isinstance(payload, dict):
                raise TypeError("add payload must be a JSON object when the stored payload is an object")
            # 检查是否有重复键
            duplicate_keys = sorted(set(current).intersection(payload))
            if duplicate_keys:
                keys = ", ".join(duplicate_keys)
                raise ValueError(f"add would overwrite existing keys: {keys}")
            updated = dict(current)
            updated.update(payload)
            self.write(namespace, key, updated)
            return updated
        raise TypeError("add requires the stored payload to be a JSON array or object")

    def exists(self, namespace: str, key: str) -> bool:
        """
        检查数据项是否存在。

        参数
        ----
        namespace : str
            命名空间
        key : str
            数据键名

        返回
        ----
        bool
            存在返回 True，否则返回 False
        """
        return self.resolve_path(namespace, key).exists()

    def delete(self, namespace: str, key: str) -> bool:
        """
        删除存储中的数据项。

        参数
        ----
        namespace : str
            命名空间
        key : str
            数据键名

        返回
        ----
        bool
            删除成功返回 True，文件不存在返回 False
        """
        path = self.resolve_path(namespace, key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def list_keys(self, namespace: str) -> list[str]:
        """
        列出命名空间中的所有数据键。

        参数
        ----
        namespace : str
            命名空间

        返回
        ----
        list[str]
            排序后的文件名（不含 .json 后缀）列表
        """
        namespace_dir = self.namespace_dir(namespace)
        return sorted(path.name for path in namespace_dir.glob("*.json"))
