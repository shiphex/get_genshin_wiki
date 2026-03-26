"""存储模块 - 书籍数据写入"""
import json
import logging
from pathlib import Path

from src.parser.book_parser import Book

logger = logging.getLogger(__name__)


class BookStorage:
    """书籍数据存储器"""

    def __init__(self, base_dir: str = "storage/book"):
        self.base_dir = Path(base_dir)
        self.raw_dir = self.base_dir / "raw"
        self.clean_dir = self.base_dir / "cleaned"

        # 确保目录存在
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.clean_dir.mkdir(parents=True, exist_ok=True)

        self.books_file = self.base_dir / "books.jsonl"
        self.failed_file = self.base_dir / "failed_books.txt"

    def save_book(self, book: Book) -> None:
        """保存单本书籍数据

        Args:
            book: Book 对象
        """
        try:
            # 保存为 JSONL（结构化数据）
            with open(self.books_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(book.to_dict(), ensure_ascii=False) + "\n")

            # 保存清洗后的纯文本
            clean_file = self.clean_dir / f"{book.title}.txt"
            with open(clean_file, "w", encoding="utf-8") as f:
                # 写入书籍信息
                f.write(f"# {book.info.name}\n\n")
                if book.info.obtain_method:
                    f.write(f"获取方式：{book.info.obtain_method}\n\n")
                f.write("## 章节\n\n")
                for volume in book.volumes:
                    f.write(f"### {volume.title}\n\n")
                    f.write(volume.content + "\n\n")
                    if volume.obtain_method:
                        f.write(f"获取方式：{volume.obtain_method}\n\n")

            logger.info(f"已保存书籍: {book.title}")

        except Exception as e:
            logger.error(f"保存书籍失败 {book.title}: {e}")
            raise

    def save_failed_book(self, title: str, reason: str) -> None:
        """记录失败的书籍

        Args:
            title: 书籍标题
            reason: 失败原因
        """
        with open(self.failed_file, "a", encoding="utf-8") as f:
            f.write(f"{title}\t{reason}\n")

    def load_saved_books(self) -> set[str]:
        """加载已保存的书籍标题集合

        Returns:
            已保存的书籍标题集合
        """
        saved = set()
        if self.books_file.exists():
            with open(self.books_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        saved.add(data["title"])
                    except json.JSONDecodeError:
                        continue
        return saved

    def load_failed_books(self) -> set[str]:
        """加载已失败的书籍标题集合

        Returns:
            已失败的书籍标题集合
        """
        failed = set()
        if self.failed_file.exists():
            with open(self.failed_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if parts:
                        failed.add(parts[0])
        return failed
