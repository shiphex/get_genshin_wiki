"""链接比较逻辑"""
from typing import List

from .models import LinkItem, LinkList, ComparisonResult


def compare_link_lists(remote: LinkList, local: LinkList) -> ComparisonResult:
    """比较两个链接列表，返回差异

    Args:
        remote: 远程（Wiki）链接列表
        local: 本地链接列表

    Returns:
        ComparisonResult: 包含新增、删除、未变化的链接
    """
    remote_titles = {link.title for link in remote.links}
    local_titles = {link.title for link in local.links}

    new_titles = remote_titles - local_titles
    removed_titles = local_titles - remote_titles
    unchanged_titles = remote_titles & local_titles

    # 构建结果列表，保持原始顺序
    new_links = [link for link in remote.links if link.title in new_titles]
    removed_links = [link for link in local.links if link.title in removed_titles]
    unchanged = [link for link in remote.links if link.title in unchanged_titles]

    return ComparisonResult(
        new_links=new_links,
        removed_links=removed_links,
        unchanged=unchanged,
    )


def merge_links(local: LinkList, result: ComparisonResult, keep_removed: bool = False) -> LinkList:
    """合并比较结果到本地链接列表

    Args:
        local: 本地链接列表
        result: 比较结果
        keep_removed: 是否保留已删除的链接（True=不删除，False=删除）

    Returns:
        LinkList: 合并后的链接列表
    """
    merged = LinkList(version=local.version + 1)

    # 按原始顺序添加未变化的链接
    for link in result.unchanged:
        merged.links.append(link)

    # 添加新链接
    for link in result.new_links:
        merged.links.append(link)

    # 添加保留的已删除链接（如果配置保留）
    if keep_removed:
        for link in result.removed_links:
            merged.links.append(link)

    return merged