from __future__ import annotations

import io
import unittest
from datetime import datetime, timezone

from get_genshin_wiki.progress import (
    LineProgressSink,
    NullProgressSink,
    ProgressItemFinished,
    ProgressItemStarted,
    ProgressRunFinished,
    ProgressRunStarted,
    TerminalProgressSink,
    build_progress_sink,
)


class ProgressTests(unittest.TestCase):
    def test_line_progress_sink_shows_resumed_and_skipped_items(self) -> None:
        """测试 line fallback 会把 resumed / skipped 状态写到输出里。"""
        stream = io.StringIO()
        sink = LineProgressSink(stream)
        started_at = datetime.now(timezone.utc)

        sink.run_started(
            ProgressRunStarted(
                run_id="entity:character-quests:1",
                parent_run_id=None,
                label="character-quests",
                kind="entity",
                total=2,
                pending_titles=("漩涡之遗", "漩涡之遗（系列任务）"),
                persist=True,
                page_limit=None,
                resume=True,
                started_at=started_at,
            )
        )
        sink.item_started(
            ProgressItemStarted(
                run_id="entity:character-quests:1",
                title="漩涡之遗",
                phase="resume",
                index=1,
                total=2,
                started_at=started_at,
            )
        )
        sink.item_finished(
            ProgressItemFinished(
                run_id="entity:character-quests:1",
                title="漩涡之遗",
                phase="resume",
                index=1,
                total=2,
                status="resumed",
                finished_at=started_at,
                duration_seconds=0.05,
                detail="existing output",
            )
        )
        sink.item_started(
            ProgressItemStarted(
                run_id="entity:character-quests:1",
                title="漩涡之遗（系列任务）",
                phase="crawl",
                index=2,
                total=2,
                started_at=started_at,
            )
        )
        sink.item_finished(
            ProgressItemFinished(
                run_id="entity:character-quests:1",
                title="漩涡之遗（系列任务）",
                phase="crawl",
                index=2,
                total=2,
                status="skipped",
                finished_at=started_at,
                duration_seconds=0.02,
                detail="series page",
            )
        )
        sink.run_finished(
            ProgressRunFinished(
                run_id="entity:character-quests:1",
                label="character-quests",
                kind="entity",
                status="ok",
                ok_count=0,
                failed_count=0,
                skipped_count=1,
                resumed_count=1,
                finished_at=started_at,
            )
        )

        output = stream.getvalue()
        self.assertIn("续跑", output)
        self.assertIn("跳过", output)
        self.assertIn("已存在输出", output)
        self.assertIn("系列页面", output)
        self.assertIn("传说任务", output)
        self.assertIn("进度=", output)
        self.assertIn("[#", output)

    def test_build_progress_sink_uses_null_for_non_interactive_auto_mode(self) -> None:
        """测试 auto 模式下非交互式流会禁用进度输出。"""
        sink = build_progress_sink(force=False, disabled=False, stream=io.StringIO())
        self.assertIsInstance(sink, NullProgressSink)

    def test_terminal_progress_sink_renders_chinese_table_layout(self) -> None:
        """测试 TerminalProgressSink 会输出带表格边框的中文仪表盘。"""
        stream = io.StringIO()
        sink = TerminalProgressSink(stream)
        started_at = datetime.now(timezone.utc)

        sink.run_started(
            ProgressRunStarted(
                run_id="top",
                parent_run_id=None,
                label="all",
                kind="top",
                total=3,
                pending_titles=("weapons", "characters", "artifacts"),
                persist=True,
                page_limit=None,
                resume=False,
                started_at=started_at,
            )
        )
        sink.run_started(
            ProgressRunStarted(
                run_id="entity:weapons",
                parent_run_id="top",
                label="weapons",
                kind="entity",
                total=2,
                pending_titles=("霜结的誓金枝", "渔获"),
                persist=True,
                page_limit=None,
                resume=False,
                started_at=started_at,
            )
        )
        sink.item_started(
            ProgressItemStarted(
                run_id="entity:weapons",
                title="霜结的誓金枝",
                phase="parse",
                index=1,
                total=2,
                started_at=started_at,
            )
        )
        sink.item_finished(
            ProgressItemFinished(
                run_id="entity:weapons",
                title="霜结的誓金枝",
                phase="parse",
                index=1,
                total=2,
                status="ok",
                finished_at=started_at,
                duration_seconds=0.7,
            )
        )

        output = stream.getvalue()
        self.assertIn("武器", output)
        self.assertIn("总进度", output)
        self.assertIn("当前实体", output)
        self.assertIn("当前项目", output)
        self.assertIn("最近完成", output)
        self.assertIn("待处理", output)
        self.assertIn("运行状态", output)
        self.assertIn("| 字段", output)
        self.assertIn("| 内容", output)
        self.assertIn("+----------+", output)
        self.assertIn("#", output)
        self.assertIn("霜结的誓金枝", output)


if __name__ == "__main__":
    unittest.main()
