"""Common alert rules."""

from __future__ import annotations

from .reporter import Alert


def empty_list_page(namespace: str, page_title: str) -> Alert:
    return Alert(
        level="error",
        code="empty_list_page",
        message=f"列表页未解析出任何条目: {page_title}",
        namespace=namespace,
        extra={"page_title": page_title},
    )


def missing_required_fields(namespace: str, title: str, missing_fields: list[str]) -> Alert:
    return Alert(
        level="warning",
        code="missing_required_fields",
        message=f"记录缺少关键字段: {', '.join(missing_fields)}",
        namespace=namespace,
        title=title,
        extra={"missing_fields": missing_fields},
    )


def empty_book_volumes(title: str) -> Alert:
    return Alert(
        level="error",
        code="empty_book_volumes",
        message="书籍未解析出任何卷内容",
        namespace="books",
        title=title,
    )


def invalid_artifact_piece_count(title: str, piece_count: int) -> Alert:
    return Alert(
        level="error",
        code="invalid_artifact_piece_count",
        message=f"圣遗物部件数不足 5: {piece_count}",
        namespace="artifacts",
        title=title,
        extra={"piece_count": piece_count},
    )


def writer_failure(namespace: str, title: str, reason: str) -> Alert:
    return Alert(
        level="error",
        code="writer_failure",
        message="写入失败",
        namespace=namespace,
        title=title,
        extra={"reason": reason},
    )
