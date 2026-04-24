"""链接更新检查器测试"""
import pytest

from src.linkchecker.models import LinkItem, LinkList, ComparisonResult
from src.linkchecker.comparator import compare_link_lists, merge_links


class TestLinkItem:
    """LinkItem 测试类"""

    def test_to_dict(self):
        """测试 LinkItem.to_dict()"""
        item = LinkItem(title="测试武器", url="https://wiki.biligame.com/ys/测试武器")
        result = item.to_dict()

        assert result["title"] == "测试武器"
        assert result["url"] == "https://wiki.biligame.com/ys/测试武器"

    def test_from_dict(self):
        """测试 LinkItem.from_dict()"""
        data = {"title": "测试武器", "url": "https://wiki.biligame.com/ys/测试武器"}
        item = LinkItem.from_dict(data)

        assert item.title == "测试武器"
        assert item.url == "https://wiki.biligame.com/ys/测试武器"


class TestLinkList:
    """LinkList 测试类"""

    def setup_method(self):
        """每个测试方法前 setup"""
        self.item1 = LinkItem(title="武器A", url="https://wiki.biligame.com/ys/武器A")
        self.item2 = LinkItem(title="武器B", url="https://wiki.biligame.com/ys/武器B")
        self.item3 = LinkItem(title="武器C", url="https://wiki.biligame.com/ys/武器C")

    def test_add_link(self):
        """测试添加链接"""
        link_list = LinkList()
        link_list.add_link(self.item1)

        assert len(link_list.links) == 1
        assert link_list.links[0].title == "武器A"

    def test_add_link_no_duplicate(self):
        """测试不添加重复链接"""
        link_list = LinkList()
        link_list.add_link(self.item1)
        link_list.add_link(self.item1)  # 重复添加

        assert len(link_list.links) == 1

    def test_remove_link(self):
        """测试移除链接"""
        link_list = LinkList()
        link_list.add_link(self.item1)
        link_list.add_link(self.item2)

        result = link_list.remove_link("武器A")

        assert result is True
        assert len(link_list.links) == 1
        assert link_list.links[0].title == "武器B"

    def test_remove_link_not_found(self):
        """测试移除不存在的链接"""
        link_list = LinkList()
        link_list.add_link(self.item1)

        result = link_list.remove_link("不存在的武器")

        assert result is False
        assert len(link_list.links) == 1

    def test_to_dict(self):
        """测试 LinkList.to_dict()"""
        link_list = LinkList()
        link_list.add_link(self.item1)
        link_list.add_link(self.item2)
        link_list.updated_at = "2026-04-24T00:00:00"
        link_list.version = 2

        result = link_list.to_dict()

        assert len(result["links"]) == 2
        assert result["updated_at"] == "2026-04-24T00:00:00"
        assert result["version"] == 2

    def test_from_dict(self):
        """测试 LinkList.from_dict()"""
        data = {
            "links": [
                {"title": "武器A", "url": "https://wiki.biligame.com/ys/武器A"},
                {"title": "武器B", "url": "https://wiki.biligame.com/ys/武器B"},
            ],
            "updated_at": "2026-04-24T00:00:00",
            "version": 3,
        }

        link_list = LinkList.from_dict(data)

        assert len(link_list.links) == 2
        assert link_list.links[0].title == "武器A"
        assert link_list.updated_at == "2026-04-24T00:00:00"
        assert link_list.version == 3


class TestComparisonResult:
    """ComparisonResult 测试类"""

    def test_has_updates_true(self):
        """测试 has_updates 为 True 的情况"""
        result = ComparisonResult(
            new_links=[LinkItem(title="A", url="http://a.com")],
            removed_links=[],
            unchanged=[],
        )

        assert result.has_updates is True

    def test_has_updates_true_removed(self):
        """测试有删除项时 has_updates 为 True"""
        result = ComparisonResult(
            new_links=[],
            removed_links=[LinkItem(title="A", url="http://a.com")],
            unchanged=[],
        )

        assert result.has_updates is True

    def test_has_updates_false(self):
        """测试没有更新时 has_updates 为 False"""
        result = ComparisonResult(
            new_links=[],
            removed_links=[],
            unchanged=[LinkItem(title="A", url="http://a.com")],
        )

        assert result.has_updates is False


class TestCompareLinkLists:
    """compare_link_lists 测试类"""

    def test_all_new(self):
        """测试远程全是新链接的情况"""
        remote = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
            LinkItem(title="武器B", url="http://b.com"),
        ])
        local = LinkList()

        result = compare_link_lists(remote, local)

        assert len(result.new_links) == 2
        assert len(result.removed_links) == 0
        assert len(result.unchanged) == 0

    def test_all_unchanged(self):
        """测试本地和远程相同的情况"""
        remote = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
            LinkItem(title="武器B", url="http://b.com"),
        ])
        local = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
            LinkItem(title="武器B", url="http://b.com"),
        ])

        result = compare_link_lists(remote, local)

        assert len(result.new_links) == 0
        assert len(result.removed_links) == 0
        assert len(result.unchanged) == 2

    def test_mixed(self):
        """测试混合情况"""
        remote = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
            LinkItem(title="武器B", url="http://b.com"),
            LinkItem(title="武器C", url="http://c.com"),
        ])
        local = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
            LinkItem(title="武器D", url="http://d.com"),  # 本地有，远程没有
        ])

        result = compare_link_lists(remote, local)

        # 远程有 B、C 本地没有 -> new
        assert len(result.new_links) == 2
        assert {l.title for l in result.new_links} == {"武器B", "武器C"}

        # 本地有 D 远程没有 -> removed
        assert len(result.removed_links) == 1
        assert result.removed_links[0].title == "武器D"

        # A 两者都有 -> unchanged
        assert len(result.unchanged) == 1
        assert result.unchanged[0].title == "武器A"

    def test_preserve_order(self):
        """测试保持原始顺序"""
        remote = LinkList(links=[
            LinkItem(title="武器C", url="http://c.com"),
            LinkItem(title="武器A", url="http://a.com"),
            LinkItem(title="武器B", url="http://b.com"),
        ])
        local = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
        ])

        result = compare_link_lists(remote, local)

        # 保持远程的顺序
        assert result.unchanged[0].title == "武器A"
        # new_links = C, B（远程有但本地没有的，按远程顺序）
        assert result.new_links[0].title == "武器C"
        assert result.new_links[1].title == "武器B"


class TestMergeLinks:
    """merge_links 测试类"""

    def test_merge_with_new(self):
        """测试合并新链接"""
        local = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
        ])
        result = ComparisonResult(
            new_links=[
                LinkItem(title="武器B", url="http://b.com"),
            ],
            removed_links=[],
            unchanged=[LinkItem(title="武器A", url="http://a.com")],
        )

        merged = merge_links(local, result, keep_removed=False)

        assert len(merged.links) == 2
        assert {l.title for l in merged.links} == {"武器A", "武器B"}
        assert merged.version == 2

    def test_merge_with_removed_keep(self):
        """测试合并时保留已删除链接"""
        local = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
        ])
        result = ComparisonResult(
            new_links=[],
            removed_links=[LinkItem(title="武器B", url="http://b.com")],
            unchanged=[LinkItem(title="武器A", url="http://a.com")],
        )

        merged = merge_links(local, result, keep_removed=True)

        assert len(merged.links) == 2
        assert {l.title for l in merged.links} == {"武器A", "武器B"}

    def test_merge_with_removed_no_keep(self):
        """测试合并时不保留已删除链接"""
        local = LinkList(links=[
            LinkItem(title="武器A", url="http://a.com"),
        ])
        result = ComparisonResult(
            new_links=[],
            removed_links=[LinkItem(title="武器B", url="http://b.com")],
            unchanged=[LinkItem(title="武器A", url="http://a.com")],
        )

        merged = merge_links(local, result, keep_removed=False)

        assert len(merged.links) == 1
        assert merged.links[0].title == "武器A"