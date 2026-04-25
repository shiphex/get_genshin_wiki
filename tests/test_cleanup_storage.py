import json
from pathlib import Path

from src.storage.cleanup import cleanup_paths, collect_cleanup_targets


def test_collect_cleanup_targets_supports_project_and_type_filters(tmp_path: Path):
    workspace = tmp_path / "workspace"
    storage_root = workspace / "storage"
    tests_output = workspace / "tests" / "output"

    (storage_root / "books" / "raw").mkdir(parents=True)
    (storage_root / "books" / "alerts").mkdir(parents=True)
    (storage_root / "books" / "cleaned").mkdir(parents=True)
    (storage_root / "books" / "structured").mkdir(parents=True)
    tests_output.mkdir(parents=True)

    (storage_root / "books" / "raw" / "book.html").write_text("<html></html>", encoding="utf-8")
    (storage_root / "books" / "alerts" / "alerts_1.json").write_text("[]", encoding="utf-8")
    (storage_root / "books" / "cleaned" / "books.json").write_text(json.dumps([]), encoding="utf-8")
    (storage_root / "books" / "cleaned" / "books.json.bak").write_text(json.dumps([]), encoding="utf-8")
    (storage_root / "books" / "cleaned" / "legacy.txt").write_text("legacy", encoding="utf-8")
    (storage_root / "books" / "structured" / "books.jsonl").write_text("", encoding="utf-8")
    (tests_output / "sample.json").write_text("{}", encoding="utf-8")

    targets = collect_cleanup_targets(
        storage_config={"output_dir": str(storage_root)},
        projects=["books", "tests", "final-json"],
        file_types=["html", "json"],
        root_dir=workspace,
    )

    relative_targets = {path.relative_to(workspace).as_posix() for path in targets}
    assert "storage/books/raw/book.html" in relative_targets
    assert "storage/books/alerts/alerts_1.json" in relative_targets
    assert "tests/output/sample.json" in relative_targets
    assert "storage/books/cleaned/books.json" in relative_targets
    assert "storage/books/cleaned/books.json.bak" in relative_targets
    assert "storage/books/cleaned/legacy.txt" not in relative_targets
    assert "storage/books/structured/books.jsonl" not in relative_targets


def test_cleanup_paths_removes_cache_and_selected_files(tmp_path: Path):
    workspace = tmp_path / "workspace"
    output_file = workspace / "tests" / "output" / "sample.json"
    cache_dir = workspace / "src" / "__pycache__"
    log_file = workspace / "logs" / "crawler.log"

    output_file.parent.mkdir(parents=True)
    cache_dir.mkdir(parents=True)
    log_file.parent.mkdir(parents=True)

    output_file.write_text("{}", encoding="utf-8")
    (cache_dir / "module.pyc").write_bytes(b"pyc")
    log_file.write_text("log", encoding="utf-8")

    targets = collect_cleanup_targets(
        storage_config={"output_dir": str(workspace / "storage")},
        projects=["tests"],
        file_types=["json"],
        include_cache=True,
        include_logs=True,
        root_dir=workspace,
    )
    result = cleanup_paths(targets)

    assert result.removed_count == 3
    assert not output_file.exists()
    assert not cache_dir.exists()
    assert not log_file.exists()
