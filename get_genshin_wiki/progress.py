from __future__ import annotations

import os
import shutil
import sys
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol, TextIO

ProgressRunKind = Literal["top", "entity"]
ProgressStatus = Literal["ok", "failed", "skipped", "resumed"]

_RUN_LABELS: dict[str, str] = {
    "all": "全部任务",
    "weapons": "武器",
    "artifacts": "圣遗物",
    "monsters": "怪物",
    "books": "书籍",
    "foods": "食物",
    "wildlife": "野生生物",
    "quest-items": "任务道具",
    "items": "物品",
    "materials": "材料",
    "namecards": "名片",
    "secret-items": "隐藏道具",
    "characters": "角色",
    "event-quests": "活动任务",
    "chronicles": "编年史",
    "north-library": "北陆图书馆",
    "archon-quests": "魔神任务",
    "character-quests": "传说任务",
}
_PHASE_LABELS: dict[str, str] = {
    "run": "执行",
    "discover": "发现",
    "crawl": "抓取",
    "crawl-voice": "抓取语音",
    "crawl-event": "抓取活动",
    "parse": "解析",
    "persist": "保存",
    "resume": "续跑",
}
_STATUS_LABELS: dict[str, str] = {
    "ok": "成功",
    "failed": "失败",
    "skipped": "跳过",
    "resumed": "续跑",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProgressRunStarted:
    run_id: str
    parent_run_id: str | None
    label: str
    kind: ProgressRunKind
    total: int
    pending_titles: tuple[str, ...]
    persist: bool
    page_limit: int | None
    resume: bool
    started_at: datetime


@dataclass(frozen=True)
class ProgressItemStarted:
    run_id: str
    title: str
    phase: str
    index: int
    total: int
    started_at: datetime


@dataclass(frozen=True)
class ProgressItemUpdated:
    run_id: str
    title: str
    phase: str
    index: int
    total: int
    updated_at: datetime


@dataclass(frozen=True)
class ProgressItemFinished:
    run_id: str
    title: str
    phase: str
    index: int
    total: int
    status: ProgressStatus
    finished_at: datetime
    duration_seconds: float
    detail: str = ""


@dataclass(frozen=True)
class ProgressItemFailed:
    run_id: str
    title: str
    phase: str
    index: int
    total: int
    finished_at: datetime
    duration_seconds: float
    error: str


@dataclass(frozen=True)
class ProgressRunFinished:
    run_id: str
    label: str
    kind: ProgressRunKind
    status: Literal["ok", "failed"]
    ok_count: int
    failed_count: int
    skipped_count: int
    resumed_count: int
    finished_at: datetime


class ProgressSink(Protocol):
    def run_started(self, event: ProgressRunStarted) -> None: ...

    def item_started(self, event: ProgressItemStarted) -> None: ...

    def item_updated(self, event: ProgressItemUpdated) -> None: ...

    def item_finished(self, event: ProgressItemFinished) -> None: ...

    def item_failed(self, event: ProgressItemFailed) -> None: ...

    def run_finished(self, event: ProgressRunFinished) -> None: ...


class NullProgressSink:
    def run_started(self, event: ProgressRunStarted) -> None:
        return None

    def item_started(self, event: ProgressItemStarted) -> None:
        return None

    def item_updated(self, event: ProgressItemUpdated) -> None:
        return None

    def item_finished(self, event: ProgressItemFinished) -> None:
        return None

    def item_failed(self, event: ProgressItemFailed) -> None:
        return None

    def run_finished(self, event: ProgressRunFinished) -> None:
        return None


class LineProgressSink:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stderr
        self._run_labels: dict[str, str] = {}
        self._run_totals: dict[str, int] = {}

    def run_started(self, event: ProgressRunStarted) -> None:
        self._run_labels[event.run_id] = event.label
        self._run_totals[event.run_id] = event.total
        self._write(
            f"[{_display_name(event.label)}] 启动 进度={_progress_text(0, event.total, width=12)} "
            f"持久化={_yes_no(event.persist)} 页数限制={_page_limit_text(event.page_limit)} "
            f"续跑模式={_yes_no(event.resume)} 待处理={_preview_titles(event.pending_titles)}"
        )

    def item_started(self, event: ProgressItemStarted) -> None:
        self._write(
            f"{self._item_prefix(event)} 开始 阶段={_phase_text(event.phase)} 标题={_display_name(event.title)}"
        )

    def item_updated(self, event: ProgressItemUpdated) -> None:
        self._write(
            f"{self._item_prefix(event)} 更新 阶段={_phase_text(event.phase)} 标题={_display_name(event.title)}"
        )

    def item_finished(self, event: ProgressItemFinished) -> None:
        detail = _detail_text(event.detail)
        suffix = f" 说明={detail}" if detail else ""
        self._write(
            f"{self._item_prefix(event)} {_status_text(event.status)} "
            f"阶段={_phase_text(event.phase)} 标题={_display_name(event.title)} "
            f"耗时={event.duration_seconds:.2f}秒{suffix}"
        )

    def item_failed(self, event: ProgressItemFailed) -> None:
        self._write(
            f"{self._item_prefix(event)} 失败 阶段={_phase_text(event.phase)} "
            f"标题={_display_name(event.title)} 耗时={event.duration_seconds:.2f}秒 错误={event.error}"
        )

    def run_finished(self, event: ProgressRunFinished) -> None:
        finished = event.ok_count + event.failed_count + event.skipped_count + event.resumed_count
        total = self._run_totals.get(event.run_id, finished)
        self._write(
            f"[{_display_name(event.label)}] 完成 进度={_progress_text(finished, total, width=12)} "
            f"状态={_status_text(event.status)} 成功={event.ok_count} 失败={event.failed_count} "
            f"跳过={event.skipped_count} 续跑={event.resumed_count}"
        )
        self._run_labels.pop(event.run_id, None)
        self._run_totals.pop(event.run_id, None)

    def _write(self, line: str) -> None:
        self._stream.write(f"{line}\n")
        self._stream.flush()

    def _item_prefix(
        self,
        event: ProgressItemStarted | ProgressItemUpdated | ProgressItemFinished | ProgressItemFailed,
    ) -> str:
        label = self._run_labels.get(event.run_id, event.run_id)
        return f"[{_display_name(label)}] {event.index}/{event.total}"


@dataclass
class _RunState:
    run_id: str
    parent_run_id: str | None
    label: str
    kind: ProgressRunKind
    total: int
    pending_titles: tuple[str, ...]
    persist: bool
    page_limit: int | None
    resume: bool
    started_at: datetime
    current_title: str = ""
    current_phase: str = ""
    current_index: int = 0
    ok_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    resumed_count: int = 0
    recent: deque[str] = field(default_factory=lambda: deque(maxlen=5))

    @property
    def finished_units(self) -> int:
        return self.ok_count + self.failed_count + self.skipped_count + self.resumed_count

    def pending_preview(self) -> list[str]:
        cursor = self.current_index if self.current_title else self.finished_units
        return list(self.pending_titles[cursor : cursor + 3])


class TerminalProgressSink:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stderr
        self._states: dict[str, _RunState] = {}
        self._active_run_order: list[str] = []
        self._line_count = 0

    def run_started(self, event: ProgressRunStarted) -> None:
        self._states[event.run_id] = _RunState(
            run_id=event.run_id,
            parent_run_id=event.parent_run_id,
            label=event.label,
            kind=event.kind,
            total=event.total,
            pending_titles=event.pending_titles,
            persist=event.persist,
            page_limit=event.page_limit,
            resume=event.resume,
            started_at=event.started_at,
        )
        self._active_run_order.append(event.run_id)
        self._render()

    def item_started(self, event: ProgressItemStarted) -> None:
        state = self._states.get(event.run_id)
        if state is None:
            return
        state.current_title = event.title
        state.current_phase = event.phase
        state.current_index = event.index
        self._render()

    def item_updated(self, event: ProgressItemUpdated) -> None:
        state = self._states.get(event.run_id)
        if state is None:
            return
        state.current_title = event.title
        state.current_phase = event.phase
        state.current_index = event.index
        self._render()

    def item_finished(self, event: ProgressItemFinished) -> None:
        state = self._states.get(event.run_id)
        if state is None:
            return
        state.current_title = event.title
        state.current_phase = event.phase
        state.current_index = event.index
        if event.status == "ok":
            state.ok_count += 1
        elif event.status == "skipped":
            state.skipped_count += 1
        else:
            state.resumed_count += 1
        state.recent.append(_recent_entry(event.status, event.title, event.duration_seconds))
        self._render()

    def item_failed(self, event: ProgressItemFailed) -> None:
        state = self._states.get(event.run_id)
        if state is None:
            return
        state.current_title = event.title
        state.current_phase = event.phase
        state.current_index = event.index
        state.failed_count += 1
        state.recent.append(_recent_entry("failed", event.title, event.duration_seconds))
        self._render()

    def run_finished(self, event: ProgressRunFinished) -> None:
        state = self._states.get(event.run_id)
        if state is None:
            return
        state.ok_count = event.ok_count
        state.failed_count = event.failed_count
        state.skipped_count = event.skipped_count
        state.resumed_count = event.resumed_count
        self._render()
        self._active_run_order = [run_id for run_id in self._active_run_order if run_id != event.run_id]
        self._states.pop(event.run_id, None)
        if not self._active_run_order:
            self._stream.write("\n")
            self._stream.flush()
            self._line_count = 0
            return
        self._render()

    def _render(self) -> None:
        lines = self._snapshot_lines()
        if not lines:
            return
        previous_line_count = self._line_count
        if previous_line_count:
            self._stream.write("\r")
            if previous_line_count > 1:
                self._stream.write(f"\x1b[{previous_line_count - 1}A")
        render_lines = list(lines)
        if previous_line_count > len(render_lines):
            render_lines.extend([""] * (previous_line_count - len(render_lines)))
        for index, line in enumerate(render_lines):
            self._stream.write("\x1b[2K")
            self._stream.write(line)
            if index < len(render_lines) - 1:
                self._stream.write("\n")
        self._stream.flush()
        self._line_count = len(lines)

    def _snapshot_lines(self) -> list[str]:
        if not self._active_run_order:
            return []
        width = min(shutil.get_terminal_size(fallback=(100, 20)).columns, 120)
        root = self._states[self._active_run_order[0]]
        leaf = self._states[self._active_run_order[-1]]
        rows = self._build_rows(root, leaf, width)
        return _render_table(rows, width)

    def _build_rows(self, root: _RunState, leaf: _RunState, width: int) -> list[tuple[str, str]]:
        bar_width = _table_bar_width(width)
        rows: list[tuple[str, str]] = []
        if root.kind == "top":
            rows.append(
                (
                    "总进度",
                    f"{_render_bar(root.finished_units, root.total, bar_width)} "
                    f"{root.finished_units}/{root.total} ({_format_percent(root.finished_units, root.total)}) "
                    f"| 用时 {_elapsed(root.started_at)}",
                )
            )
        rows.append(("当前实体", self._entity_row(root, leaf, bar_width)))
        rows.append(("当前项目", self._current_row(root, leaf)))
        rows.append(("最近完成", self._done_row(leaf)))
        rows.append(("待处理", self._pending_row(root, leaf)))
        rows.append(("运行状态", self._status_row(root, leaf)))
        return rows

    def _entity_row(self, root: _RunState, leaf: _RunState, bar_width: int) -> str:
        active_state = leaf if leaf.run_id != root.run_id else root
        if active_state.kind == "top":
            next_entities = _preview_titles(tuple(root.pending_preview()))
            if root.current_title:
                return f"{_display_name(root.current_title)} | 等待条目队列"
            return f"等待启动 | 下一实体 {next_entities}"
        return (
            f"{_display_name(active_state.label)} "
            f"{_render_bar(active_state.finished_units, active_state.total, bar_width)} "
            f"{active_state.finished_units}/{active_state.total} "
            f"({_format_percent(active_state.finished_units, active_state.total)}) "
            f"| 用时 {_elapsed(active_state.started_at)}"
        )

    def _current_row(self, root: _RunState, leaf: _RunState) -> str:
        if leaf.current_title:
            if root.kind == "top" and leaf.run_id != root.run_id:
                return (
                    f"{_display_name(leaf.label)} / {_phase_text(leaf.current_phase)} "
                    f"/ {_display_name(leaf.current_title)}"
                )
            else:
                return f"{_phase_text(leaf.current_phase)} / {_display_name(leaf.current_title)}"
        if root.kind == "top" and root.current_title:
            return f"{_display_name(root.current_title)} | 等待条目开始"
        return "空闲"

    def _done_row(self, leaf: _RunState) -> str:
        recent = " | ".join(leaf.recent) if leaf.recent else "暂无"
        return recent

    def _pending_row(self, root: _RunState, leaf: _RunState) -> str:
        next_entities = _preview_titles(tuple(root.pending_preview())) if root.kind == "top" else ""
        next_items = _preview_titles(tuple(leaf.pending_preview())) if leaf.pending_preview() else ""
        if root.kind == "top" and leaf.run_id != root.run_id:
            return f"下一实体 {next_entities or '无'} | 下一批 {next_items or '无'}"
        if root.kind == "top":
            return f"下一实体 {next_entities or '无'}"
        return f"下一批 {next_items or '无'}"

    def _status_row(self, root: _RunState, leaf: _RunState) -> str:
        resume_mode = leaf.resume if leaf.run_id != root.run_id else root.resume
        return (
            f"持久化={_yes_no(root.persist)} | 页数限制={_page_limit_text(root.page_limit)} "
            f"| 续跑模式={_yes_no(resume_mode)} | 成功={leaf.ok_count} | 失败={leaf.failed_count} "
            f"| 跳过={leaf.skipped_count} | 续跑={leaf.resumed_count}"
        )


def build_progress_sink(
    *,
    force: bool,
    disabled: bool,
    stream: TextIO | None = None,
) -> ProgressSink:
    output = stream or sys.stderr
    if disabled:
        return NullProgressSink()
    if _supports_ansi(output):
        return TerminalProgressSink(output)
    if force or _is_interactive(output):
        return LineProgressSink(output)
    return NullProgressSink()


def _supports_ansi(stream: TextIO) -> bool:
    if not _is_interactive(stream):
        return False
    if os.environ.get("NO_COLOR"):
        return False
    term = os.environ.get("TERM", "")
    return term.lower() != "dumb"


def _is_interactive(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(callable(isatty) and isatty())


def _elapsed(started_at: datetime, finished_at: datetime | None = None) -> str:
    end = finished_at or _utc_now()
    delta = max(0, int((end - started_at).total_seconds()))
    hours, remainder = divmod(delta, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_percent(done: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{(done / total) * 100:.1f}%"


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _display_name(value: str) -> str:
    return _RUN_LABELS.get(value, value)


def _phase_text(value: str) -> str:
    return _PHASE_LABELS.get(value, value)


def _status_text(value: str) -> str:
    return _STATUS_LABELS.get(value, value)


def _detail_text(value: str) -> str:
    detail = value.strip()
    if not detail:
        return ""
    if detail == "existing output":
        return "已存在输出"
    if detail == "series page":
        return "系列页面"
    if detail.startswith("duplicate "):
        return f"重复：{_display_name(detail[len('duplicate '):])}"
    if detail.startswith("selected="):
        return f"已选取={detail[len('selected='):]}"
    return detail


def _page_limit_text(page_limit: int | None) -> str:
    return "不限" if page_limit is None else str(page_limit)


def _preview_titles(titles: tuple[str, ...]) -> str:
    if not titles:
        return "无"
    return "、".join(_display_name(title) for title in titles[:3])


def _recent_entry(status: str, title: str, duration_seconds: float) -> str:
    return f"[{_status_text(status)}] {_display_name(title)} {duration_seconds:.1f}秒"


def _bar_width(total_width: int) -> int:
    return max(10, min(24, total_width // 4))


def _table_bar_width(total_width: int) -> int:
    return max(8, min(18, total_width // 6))


def _progress_text(done: int, total: int, *, width: int) -> str:
    return f"{_render_bar(done, total, width)} {done}/{total} ({_format_percent(done, total)})"


def _render_bar(done: int, total: int, width: int) -> str:
    if width <= 0:
        return "[]"
    if total <= 0 or done <= 0:
        filled = 0
    else:
        filled = min(width, max(0, round((done / total) * width)))
        if done >= total:
            filled = width
    return f"[{'#' * filled}{'.' * (width - filled)}]"


def _render_table(rows: list[tuple[str, str]], total_width: int) -> list[str]:
    if not rows:
        return []

    max_label_width = max(_display_width("字段"), *(_display_width(label) for label, _ in rows))
    minimum_content_width = 12 if total_width >= 28 else 4
    label_width = min(max_label_width, max(4, total_width - minimum_content_width - 7))
    content_width = max(4, total_width - label_width - 7)

    border = f"+-{'-' * label_width}-+-{'-' * content_width}-+"
    lines = [
        border,
        _render_table_line("字段", label_width, "内容", content_width),
        border,
    ]
    for label, content in rows:
        label_lines = _wrap_display(label, label_width)
        content_lines = _wrap_display(content, content_width)
        row_height = max(len(label_lines), len(content_lines))
        for index in range(row_height):
            lines.append(
                _render_table_line(
                    label_lines[index] if index < len(label_lines) else "",
                    label_width,
                    content_lines[index] if index < len(content_lines) else "",
                    content_width,
                )
            )
    lines.append(border)
    return lines


def _render_table_line(label: str, label_width: int, content: str, content_width: int) -> str:
    return f"| {_pad_display(label, label_width)} | {_pad_display(content, content_width)} |"


def _wrap_display(text: str, width: int) -> list[str]:
    if width <= 0:
        return [""]
    stripped = text.strip()
    if not stripped:
        return [""]

    lines: list[str] = []
    remaining = stripped
    while remaining:
        chunk, remaining = _split_display_chunk(remaining, width)
        lines.append(chunk.rstrip())
        remaining = remaining.lstrip()
    return lines or [""]


def _split_display_chunk(text: str, width: int) -> tuple[str, str]:
    current_width = 0
    last_break = -1
    for index, char in enumerate(text):
        char_width = _char_display_width(char)
        if current_width + char_width > width:
            if last_break > 0:
                return text[:last_break].rstrip(), text[last_break:].lstrip()
            if index == 0:
                return char, text[1:].lstrip()
            return text[:index].rstrip(), text[index:].lstrip()
        current_width += char_width
        if char in {" ", "|", "、", "/", ",", "，"}:
            last_break = index + 1
    return text.rstrip(), ""


def _pad_display(text: str, width: int) -> str:
    padding = max(0, width - _display_width(text))
    return f"{text}{' ' * padding}"


def _display_width(text: str) -> int:
    return sum(_char_display_width(char) for char in text)


def _char_display_width(char: str) -> int:
    if char == "\n":
        return 0
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in {"W", "F"}:
        return 2
    return 1
