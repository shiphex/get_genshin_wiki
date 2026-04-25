import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.storage.cleaned_store import CleanedStore, CleanedStoreCorruptionError
from src.storage.layout import build_storage_layout


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_store(tmp_path: Path) -> tuple[CleanedStore, Path, Path, Path]:
    layout = build_storage_layout({"output_dir": str(tmp_path / "storage")}, "books")
    store = CleanedStore(
        layout.cleaned_file,
        temp_file_path=layout.cleaned_temp_file,
        backup_file_path=layout.cleaned_backup_file,
    )
    return store, layout.cleaned_file, layout.cleaned_temp_file, layout.cleaned_backup_file


def test_cleaned_store_raises_explicit_error_for_corrupt_json(tmp_path: Path):
    store, cleaned_file, _, backup_file = _build_store(tmp_path)
    cleaned_file.write_text('[{"title": "broken"}', encoding="utf-8")
    backup_file.write_text("[]", encoding="utf-8")

    with pytest.raises(CleanedStoreCorruptionError, match="corrupted"):
        store.save("new-book", "new content")

    assert cleaned_file.read_text(encoding="utf-8") == '[{"title": "broken"}'


def test_cleaned_store_keeps_previous_version_backup(tmp_path: Path):
    store, cleaned_file, _, backup_file = _build_store(tmp_path)

    store.save("book", "first version")
    store.save("book", "second version")

    current_records = json.loads(cleaned_file.read_text(encoding="utf-8"))
    backup_records = json.loads(backup_file.read_text(encoding="utf-8"))

    assert current_records[0]["content_clean"] == "second version"
    assert backup_records[0]["content_clean"] == "first version"


def test_cleaned_store_write_failure_keeps_previous_file_and_cleans_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store, cleaned_file, temp_file, _ = _build_store(tmp_path)
    store.save("book", "stable version")

    def fail_after_partial_temp_write(content: str) -> None:
        with temp_file.open("w", encoding="utf-8", newline="\n") as file:
            file.write(content[:20])
            file.flush()
            os.fsync(file.fileno())
        raise OSError("No space left on device")

    monkeypatch.setattr(store, "_write_temp_file", fail_after_partial_temp_write)

    with pytest.raises(OSError, match="No space left on device"):
        store.save("book", "broken version")

    records = json.loads(cleaned_file.read_text(encoding="utf-8"))

    assert records[0]["content_clean"] == "stable version"
    assert not temp_file.exists()


def test_cleaned_store_atomic_write_survives_killed_process(tmp_path: Path):
    store, cleaned_file, temp_file, backup_file = _build_store(tmp_path)
    marker_file = cleaned_file.parent / "replace-ready.marker"
    store.save("book", "stable version")

    script = """
import sys
import time
from pathlib import Path

from src.storage.cleaned_store import CleanedStore


class SlowReplaceStore(CleanedStore):
    def __init__(self, marker_path: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.marker_path = Path(marker_path)

    def _replace_file(self, source, destination, copy_source=False):
        if not copy_source and Path(source) == self.temp_file_path and Path(destination) == self.file_path:
            self.marker_path.write_text("ready", encoding="utf-8")
            time.sleep(30)
        super()._replace_file(source, destination, copy_source=copy_source)


store = SlowReplaceStore(
    sys.argv[4],
    sys.argv[1],
    temp_file_path=sys.argv[2],
    backup_file_path=sys.argv[3],
)
store.save("book", "interrupted version")
"""

    env = os.environ.copy()
    python_path = str(PROJECT_ROOT)
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.pathsep.join([python_path, env["PYTHONPATH"]])
    else:
        env["PYTHONPATH"] = python_path
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(cleaned_file), str(temp_file), str(backup_file), str(marker_file)],
        cwd=PROJECT_ROOT,
        env=env,
    )

    deadline = time.time() + 10
    while time.time() < deadline and not marker_file.exists():
        if process.poll() is not None:
            break
        time.sleep(0.05)

    assert marker_file.exists(), "Child process did not reach the pre-replace stage."

    process.kill()
    process.wait(timeout=5)

    records = json.loads(cleaned_file.read_text(encoding="utf-8"))
    backup_records = json.loads(backup_file.read_text(encoding="utf-8"))

    assert records[0]["content_clean"] == "stable version"
    assert backup_records[0]["content_clean"] == "stable version"
    assert temp_file.exists()

    loaded_records = store._load_records()

    assert loaded_records[0]["content_clean"] == "stable version"
    assert not temp_file.exists()
