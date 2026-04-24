"""链接更新检查器数据模型"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class LinkItem:
    """链接项"""
    title: str
    url: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LinkItem":
        return cls(
            title=data["title"],
            url=data["url"],
        )


@dataclass
class LinkList:
    """链接列表（含元数据）"""
    links: List[LinkItem] = field(default_factory=list)
    updated_at: str = ""
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "links": [link.to_dict() for link in self.links],
            "updated_at": self.updated_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LinkList":
        return cls(
            links=[LinkItem.from_dict(item) for item in data.get("links", [])],
            updated_at=data.get("updated_at", ""),
            version=data.get("version", 1),
        )

    def add_link(self, link: LinkItem) -> None:
        """添加链接（不重复）"""
        if not any(l.title == link.title for l in self.links):
            self.links.append(link)

    def remove_link(self, title: str) -> bool:
        """移除指定标题的链接，返回是否成功"""
        for i, link in enumerate(self.links):
            if link.title == title:
                self.links.pop(i)
                return True
        return False


@dataclass
class ComparisonResult:
    """比较结果"""
    new_links: List[LinkItem] = field(default_factory=list)
    removed_links: List[LinkItem] = field(default_factory=list)
    unchanged: List[LinkItem] = field(default_factory=list)

    @property
    def has_updates(self) -> bool:
        return len(self.new_links) > 0 or len(self.removed_links) > 0

    def to_dict(self) -> dict:
        return {
            "new_links": [link.to_dict() for link in self.new_links],
            "removed_links": [link.to_dict() for link in self.removed_links],
            "unchanged": [link.to_dict() for link in self.unchanged],
            "has_updates": self.has_updates,
        }