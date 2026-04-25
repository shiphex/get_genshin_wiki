import json
from pathlib import Path

import pytest

from src.content.books.parser import Book, BookInfo, BookVolume
from src.content.books.writer import BookStorage
from src.storage.layout import resolve_legacy_namespace_dirs, resolve_namespace_dir


def _write_jsonl(path: Path, titles: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for title in titles:
            file.write(json.dumps({"title": title, "url": f"https://example.test/{title}"}) + "\n")


def _write_failed(path: Path, titles: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for title in titles:
            file.write(f"{title}\tparse error\n")


def _read_jsonl_titles(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line)["title"] for line in file if line.strip()]


def _read_failed_titles(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as file:
        return [line.split("\t", 1)[0] for line in file if line.strip()]


def _build_book(title: str) -> Book:
    book = Book(title=title, url=f"https://example.test/{title}", fetched_at="2026-04-25T00:00:00")
    book.info = BookInfo(name=title)
    book.volumes = [BookVolume(title="Volume 1", content="Test paragraph")]
    return book


def test_saved_titles_load_from_compatible_storage_paths(tmp_path: Path):
    output_root = tmp_path / "storage"
    _write_jsonl(output_root / "books" / "books.jsonl", ["books-root"])
    _write_jsonl(output_root / "book" / "books.jsonl", ["book-root"])
    _write_jsonl(output_root / "book" / "structured" / "books.jsonl", ["book-structured"])
    _write_jsonl(output_root / "books" / "structured" / "books.jsonl", ["current-structured"])

    storage = BookStorage(storage_config={"output_dir": str(output_root)})

    assert storage.load_saved_books() == {
        "books-root",
        "book-root",
        "book-structured",
        "current-structured",
    }


def test_failed_titles_load_from_compatible_storage_paths(tmp_path: Path):
    output_root = tmp_path / "storage"
    _write_failed(output_root / "books" / "failed_books.txt", ["books-root-failed"])
    _write_failed(output_root / "book" / "failed_books.txt", ["book-root-failed"])
    _write_failed(output_root / "book" / "failed" / "failed_books.txt", ["book-failed-dir"])
    _write_failed(output_root / "books" / "failed" / "failed_books.txt", ["current-failed-dir"])

    storage = BookStorage(storage_config={"output_dir": str(output_root)})

    assert storage.load_failed_books() == {
        "books-root-failed",
        "book-root-failed",
        "book-failed-dir",
        "current-failed-dir",
    }


@pytest.mark.parametrize(
    ("namespace", "storage_config", "expected_primary", "expected_legacy"),
    [
        ("books", {"output_dir": "storage"}, Path("storage/books"), [Path("storage/book")]),
        ("arms", {"output_dir": "storage"}, Path("storage/arms"), [Path("storage/arm")]),
        ("artifacts", {"output_dir": "storage"}, Path("storage/artifacts"), []),
        (
            "books",
            {"output_dir": "storage", "books_dir": "custom/books", "book_dir": "custom/book"},
            Path("custom/books"),
            [Path("custom/book"), Path("storage/books"), Path("storage/book")],
        ),
    ],
)
def test_namespace_aliases_resolve_primary_and_legacy_paths(
    namespace: str,
    storage_config: dict[str, str],
    expected_primary: Path,
    expected_legacy: list[Path],
):
    assert resolve_namespace_dir(storage_config, namespace) == expected_primary
    assert resolve_legacy_namespace_dirs(storage_config, namespace) == expected_legacy


def test_writes_only_touch_current_layout_and_leave_legacy_data_unchanged(tmp_path: Path):
    output_root = tmp_path / "storage"
    _write_jsonl(output_root / "book" / "books.jsonl", ["legacy-saved"])
    _write_failed(output_root / "book" / "failed_books.txt", ["legacy-failed"])

    storage = BookStorage(storage_config={"output_dir": str(output_root)})
    storage.save_book(_build_book("new-book"), raw_html="<html>new-book</html>")

    assert _read_jsonl_titles(output_root / "books" / "structured" / "books.jsonl") == ["new-book"]
    assert (output_root / "books" / "raw" / "new-book.html").exists()
    assert (output_root / "books" / "cleaned" / "new-book.txt").exists()

    assert _read_jsonl_titles(output_root / "book" / "books.jsonl") == ["legacy-saved"]
    assert _read_failed_titles(output_root / "book" / "failed_books.txt") == ["legacy-failed"]
    assert not (output_root / "book" / "structured").exists()
    assert not (output_root / "book" / "raw").exists()
    assert not (output_root / "book" / "cleaned").exists()


def test_saved_and_failed_titles_are_deduplicated_across_compatible_paths(tmp_path: Path):
    output_root = tmp_path / "storage"

    _write_jsonl(output_root / "books" / "books.jsonl", ["shared", "books-root"])
    _write_jsonl(output_root / "book" / "books.jsonl", ["shared", "book-root"])
    _write_jsonl(output_root / "book" / "structured" / "books.jsonl", ["shared", "book-structured"])
    _write_jsonl(output_root / "books" / "structured" / "books.jsonl", ["shared", "current-structured"])

    _write_failed(output_root / "books" / "failed_books.txt", ["shared-failed", "books-root-failed"])
    _write_failed(output_root / "book" / "failed_books.txt", ["shared-failed", "book-root-failed"])
    _write_failed(output_root / "book" / "failed" / "failed_books.txt", ["shared-failed", "book-failed-dir"])
    _write_failed(output_root / "books" / "failed" / "failed_books.txt", ["shared-failed", "current-failed-dir"])

    storage = BookStorage(storage_config={"output_dir": str(output_root)})

    assert storage.load_saved_books() == {
        "shared",
        "books-root",
        "book-root",
        "book-structured",
        "current-structured",
    }
    assert storage.load_failed_books() == {
        "shared-failed",
        "books-root-failed",
        "book-root-failed",
        "book-failed-dir",
        "current-failed-dir",
    }
