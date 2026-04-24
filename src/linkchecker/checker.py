"""链接更新检查器核心类"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal, Union

from src.crawler.client import MediaWikiClient
from src.parser.arms_parser import ArmsParser
from src.parser.book_parser import BookParser
from src.parser.artifacts_parser import ArtifactsParser

from .models import LinkItem, LinkList, ComparisonResult
from .comparator import compare_link_lists, merge_links

logger = logging.getLogger(__name__)


class LinkChecker:
    """Wiki 内容链接更新检查器"""

    # Wiki 页面映射
    PAGE_TITLES = {
        "arms": "武器图鉴",
        "books": "书籍一览",
        "artifacts": "圣遗物图鉴",
    }

    # 解析器类映射
    PARSER_MAP = {
        "arms": ArmsParser,
        "books": BookParser,
        "artifacts": ArtifactsParser,
    }

    def __init__(
        self,
        content_type: Literal["arms", "books", "artifacts"],
        links_dir: Path,
        client: MediaWikiClient,
    ):
        """初始化链接检查器

        Args:
            content_type: 内容类型（arms/books/artifacts）
            links_dir: 链接存储目录
            client: MediaWiki 客户端
        """
        if content_type not in self.PAGE_TITLES:
            raise ValueError(f"Invalid content_type: {content_type}")

        self.content_type = content_type
        self.links_dir = Path(links_dir)
        self.client = client

        # 创建解析器
        parser_class = self.PARSER_MAP[content_type]
        self.parser = parser_class(base_url=client.base_url)

        # 链接文件路径
        self.link_file = self.links_dir / f"{content_type}.json"

        # 页面标题
        self.page_title = self.PAGE_TITLES[content_type]

    def fetch_current_links(self) -> LinkList:
        """从 Wiki 页面获取最新链接

        Returns:
            LinkList: 当前链接列表
        """
        logger.info(f"从 Wiki 获取 {self.content_type} 链接...")
        html = self.client.get_page_html(self.page_title)

        # 使用对应解析器提取链接
        if self.content_type == "arms":
            raw_links = self.parser.extract_arm_links(html)
        elif self.content_type == "books":
            raw_links = self.parser.extract_book_links(html)
        elif self.content_type == "artifacts":
            raw_links = self.parser.extract_artifact_links(html)
        else:
            raise ValueError(f"Unknown content_type: {self.content_type}")

        # 转换为 LinkItem 列表
        links = [LinkItem(title=link["title"], url=link["url"]) for link in raw_links]

        return LinkList(
            links=links,
            updated_at=datetime.now().isoformat(),
            version=1,
        )

    def load_local_links(self) -> LinkList:
        """从本地存储文件加载链接

        Returns:
            LinkList: 本地链接列表，如果文件不存在则返回空列表
        """
        if not self.link_file.exists():
            logger.info(f"本地链接文件不存在: {self.link_file}")
            return LinkList()

        with open(self.link_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return LinkList.from_dict(data)

    def save_links(self, link_list: LinkList) -> None:
        """保存链接列表到本地文件

        Args:
            link_list: 要保存的链接列表
        """
        self.links_dir.mkdir(parents=True, exist_ok=True)

        with open(self.link_file, "w", encoding="utf-8") as f:
            json.dump(link_list.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"已保存链接到: {self.link_file}")

    def compare(self, remote: LinkList, local: LinkList) -> ComparisonResult:
        """比较远程和本地链接列表

        Args:
            remote: 远程（Wiki）链接列表
            local: 本地链接列表

        Returns:
            ComparisonResult: 比较结果
        """
        return compare_link_lists(remote, local)

    def check_for_updates(self) -> ComparisonResult:
        """检查更新（获取远程并比较）

        Returns:
            ComparisonResult: 更新差异
        """
        remote = self.fetch_current_links()
        local = self.load_local_links()

        result = self.compare(remote, local)

        logger.info(
            f"检查完成: 本地 {len(local.links)} 条, "
            f"远程 {len(remote.links)} 条, "
            f"新增 {len(result.new_links)}, "
            f"删除 {len(result.removed_links)}, "
            f"未变化 {len(result.unchanged)}"
        )

        return result

    def update_links(self, result: ComparisonResult, keep_removed: bool = False) -> None:
        """更新本地链接文件

        Args:
            result: 比较结果
            keep_removed: 是否保留已删除的链接
        """
        local = self.load_local_links()
        merged = merge_links(local, result, keep_removed=keep_removed)
        merged.updated_at = datetime.now().isoformat()

        self.save_links(merged)

    def get_new_items_to_crawl(self, result: ComparisonResult) -> list[str]:
        """获取需要爬取的新项目标题列表

        Args:
            result: 比较结果

        Returns:
            list[str]: 新项目标题列表
        """
        return [link.title for link in result.new_links]

    def load_existing_titles(self) -> set[str]:
        """加载本地已存在的项目标题集合

        Returns:
            set[str]: 已存在标题集合
        """
        local = self.load_local_links()
        return {link.title for link in local.links}