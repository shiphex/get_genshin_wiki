"""Helpers for atomic text persistence with rollback support."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AtomicWriteRollbackToken:
    """State required to restore the previous file contents."""

    target_path: Path
    backup_path: Path
    existed_before: bool


def atomic_write_text(
    target_path: str | Path,
    content: str,
    *,
    temp_file_path: str | Path | None = None,
    backup_file_path: str | Path | None = None,
) -> AtomicWriteRollbackToken:
    target = Path(target_path)
    temp_path = Path(temp_file_path) if temp_file_path else target.with_suffix(f"{target.suffix}.tmp")
    backup_path = Path(backup_file_path) if backup_file_path else target.with_suffix(f"{target.suffix}.bak")

    _prepare_paths(target, temp_path, backup_path)
    _cleanup_temporary_file(temp_path)
    _cleanup_temporary_file(_destination_temp_path(backup_path))

    existed_before = target.exists()
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

        if existed_before:
            _replace_file(target, backup_path, copy_source=True)
        _replace_file(temp_path, target)
    except OSError:
        _cleanup_temporary_file(temp_path, raise_on_error=False)
        raise

    return AtomicWriteRollbackToken(target_path=target, backup_path=backup_path, existed_before=existed_before)


def atomic_append_text(
    target_path: str | Path,
    content: str,
    *,
    temp_file_path: str | Path | None = None,
    backup_file_path: str | Path | None = None,
) -> AtomicWriteRollbackToken:
    target = Path(target_path)
    temp_path = Path(temp_file_path) if temp_file_path else target.with_suffix(f"{target.suffix}.tmp")
    backup_path = Path(backup_file_path) if backup_file_path else target.with_suffix(f"{target.suffix}.bak")

    _prepare_paths(target, temp_path, backup_path)
    _cleanup_temporary_file(temp_path)
    _cleanup_temporary_file(_destination_temp_path(backup_path))

    existed_before = target.exists()
    encoded_content = content.encode("utf-8")
    try:
        with temp_path.open("wb") as file:
            if existed_before:
                with target.open("rb") as existing_file:
                    shutil.copyfileobj(existing_file, file)
            file.write(encoded_content)
            file.flush()
            os.fsync(file.fileno())

        if existed_before:
            _replace_file(target, backup_path, copy_source=True)
        _replace_file(temp_path, target)
    except OSError:
        _cleanup_temporary_file(temp_path, raise_on_error=False)
        raise

    return AtomicWriteRollbackToken(target_path=target, backup_path=backup_path, existed_before=existed_before)


def rollback_atomic_write(token: AtomicWriteRollbackToken) -> None:
    if token.existed_before:
        if not token.backup_path.exists():
            raise FileNotFoundError(f"Rollback backup file is missing: {token.backup_path}")
        _replace_file(token.backup_path, token.target_path, copy_source=True)
        return

    try:
        token.target_path.unlink()
    except FileNotFoundError:
        return


def cleanup_atomic_tempfiles(*paths: Path) -> None:
    seen_paths: set[Path] = set()
    for path in paths:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        _cleanup_temporary_file(path)


def destination_temp_path(destination: Path) -> Path:
    return _destination_temp_path(destination)


def _prepare_paths(target: Path, temp_path: Path, backup_path: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.parent.mkdir(parents=True, exist_ok=True)


def _cleanup_temporary_file(path: Path, raise_on_error: bool = True) -> None:
    if not path.exists():
        return

    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        if raise_on_error:
            raise


def _replace_file(source: Path, destination: Path, copy_source: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_destination = _destination_temp_path(destination)
    try:
        if copy_source:
            with source.open("rb") as input_file, temp_destination.open("wb") as output_file:
                shutil.copyfileobj(input_file, output_file)
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(temp_destination, destination)
        else:
            os.replace(source, destination)
    finally:
        _cleanup_temporary_file(temp_destination, raise_on_error=False)


def _destination_temp_path(destination: Path) -> Path:
    return destination.with_name(f".{destination.name}.tmp")
