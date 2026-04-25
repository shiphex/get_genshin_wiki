"""Books writer backed by shared storage modules."""

from __future__ import annotations

from src.storage.base_storage import BaseNamespaceStorage


class BookStorage(BaseNamespaceStorage):
    """书籍数据存储器"""

    namespace = "books"

    def build_clean_text(self, record) -> str:
        lines = [f"# {record.info.name}", ""]
        if record.info.obtain_method:
            lines.extend([f"获取方式：{record.info.obtain_method}", ""])
        lines.extend(["## 章节", ""])
        for volume in record.volumes:
            lines.extend([f"### {volume.title}", "", volume.content, ""])
            if volume.obtain_method:
                lines.extend([f"获取方式：{volume.obtain_method}", ""])
        return "\n".join(lines).strip() + "\n"

    def save_book(self, book, raw_html: str = "") -> None:
        self.save(record=book, raw_html=raw_html, structured=book.to_dict())

    def save_failed_book(self, title: str, reason: str) -> None:
        self.save_failed(title, reason)

    def load_saved_books(self) -> set[str]:
        return self.load_saved_titles()

    def load_failed_books(self) -> set[str]:
        return self.load_failed_titles()
