"""Storage module for saving crawled data."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from ..schema.models import WikiPage

logger = logging.getLogger(__name__)


class BaseWriter:
    """Base class for data writers."""

    def write(self, page: WikiPage) -> None:
        """Write a page to storage."""
        raise NotImplementedError

    def write_batch(self, pages: Iterator[WikiPage]) -> int:
        """Write multiple pages."""
        count = 0
        for page in pages:
            self.write(page)
            count += 1
        return count

    def close(self) -> None:
        """Close the writer."""
        pass


class JSONLWriter(BaseWriter):
    """Writer for JSONL format."""

    def __init__(self, filepath: str, mode: str = "a"):
        """
        Initialize JSONL writer.

        Args:
            filepath: Output file path
            mode: File mode ('a' for append, 'w' for write)
        """
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.file = open(self.filepath, self.mode, encoding="utf-8")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def write(self, page: WikiPage) -> None:
        """Write a page as JSON line."""
        data = page.to_dict()
        line = json.dumps(data, ensure_ascii=False)
        self.file.write(line + "\n")

    def close(self) -> None:
        """Close the file."""
        if self.file:
            self.file.close()
            self.file = None


class JSONWriter(BaseWriter):
    """Writer for JSON format."""

    def __init__(self, filepath: str):
        """
        Initialize JSON writer.

        Args:
            filepath: Output file path
        """
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.pages: list = []

    def write(self, page: WikiPage) -> None:
        """Add page to collection."""
        self.pages.append(page.to_dict())

    def save(self) -> None:
        """Save all pages to JSON file."""
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.pages, f, ensure_ascii=False, indent=2)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.save()


class SQLiteWriter(BaseWriter):
    """Writer for SQLite database."""

    def __init__(self, db_path: str):
        """
        Initialize SQLite writer.

        Args:
            db_path: Database file path
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        import sqlite3

        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

        # Create tables
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                page_id INTEGER UNIQUE,
                title TEXT NOT NULL,
                url TEXT,
                namespace INTEGER,
                source TEXT,
                fetched_at TEXT,
                content_raw TEXT,
                content_clean TEXT,
                categories TEXT,
                links TEXT,
                templates TEXT,
                infobox TEXT,
                revision TEXT,
                last_modified TEXT,
                redirect TEXT
            )
        """)

        # Create indexes
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_title ON pages(title)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_namespace ON pages(namespace)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fetched_at ON pages(fetched_at)
        """)

        self.conn.commit()

    def write(self, page: WikiPage) -> None:
        """Insert or update a page."""
        data = page.to_dict()

        # Serialize lists and dicts
        categories = json.dumps(data.get("categories", []), ensure_ascii=False)
        links = json.dumps(data.get("links", []), ensure_ascii=False)
        templates = json.dumps(data.get("templates", []), ensure_ascii=False)
        infobox = json.dumps(data.get("infobox", {}), ensure_ascii=False)
        revision = json.dumps(data.get("revision", {}), ensure_ascii=False)

        self.conn.execute("""
            INSERT OR REPLACE INTO pages (
                id, page_id, title, url, namespace, source, fetched_at,
                content_raw, content_clean, categories, links, templates,
                infobox, revision, last_modified, redirect
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("id", 0),
            data.get("page_id", 0),
            data.get("title", ""),
            data.get("url", ""),
            data.get("namespace", 0),
            data.get("source", "mediawiki"),
            data.get("fetched_at", ""),
            data.get("content_raw", ""),
            data.get("content_clean", ""),
            categories,
            links,
            templates,
            infobox,
            revision,
            data.get("last_modified"),
            data.get("redirect"),
        ))
        self.conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def query(self, sql: str, params: tuple = ()) -> list:
        """Execute query and return results."""
        cursor = self.conn.execute(sql, params)
        return cursor.fetchall()

    def get_page_by_title(self, title: str) -> Optional[Dict]:
        """Get page by title."""
        cursor = self.conn.execute(
            "SELECT * FROM pages WHERE title = ?",
            (title,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


class DataManager:
    """Manages data storage with multiple formats."""

    def __init__(self, output_dir: str):
        """
        Initialize data manager.

        Args:
            output_dir: Output directory path
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.raw_writer: Optional[JSONLWriter] = None
        self.clean_writer: Optional[JSONLWriter] = None
        self.sqlite_writer: Optional[SQLiteWriter] = None

    def get_raw_writer(self) -> JSONLWriter:
        """Get or create raw data writer."""
        if self.raw_writer is None:
            filepath = self.output_dir / "pages_raw.jsonl"
            self.raw_writer = JSONLWriter(str(filepath))
        return self.raw_writer

    def get_clean_writer(self) -> JSONLWriter:
        """Get or create clean data writer."""
        if self.clean_writer is None:
            filepath = self.output_dir / "pages_clean.jsonl"
            self.clean_writer = JSONLWriter(str(filepath))
        return self.clean_writer

    def get_sqlite_writer(self) -> SQLiteWriter:
        """Get or create SQLite writer."""
        if self.sqlite_writer is None:
            filepath = self.output_dir / "wiki.db"
            self.sqlite_writer = SQLiteWriter(str(filepath))
        return self.sqlite_writer

    def write_raw(self, page: WikiPage) -> None:
        """Write raw page data."""
        writer = self.get_raw_writer()
        writer.write(page)

    def write_clean(self, page: WikiPage) -> None:
        """Write cleaned page data."""
        writer = self.get_clean_writer()
        writer.write(page)

    def write_all(self, page: WikiPage) -> None:
        """Write to all storage formats."""
        self.write_raw(page)
        self.write_clean(page)
        self.get_sqlite_writer().write(page)

    def close(self) -> None:
        """Close all writers."""
        if self.raw_writer:
            self.raw_writer.close()
            self.raw_writer = None
        if self.clean_writer:
            self.clean_writer.close()
            self.clean_writer = None
        if self.sqlite_writer:
            self.sqlite_writer.close()
            self.sqlite_writer = None
