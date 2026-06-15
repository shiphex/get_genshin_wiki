# Feature Spec: Lightweight Terminal Progress UI

> This file was generated during worktree setup to guide implementation in this branch.

## Branch Info

| Item | Value |
|------|-------|
| Branch name | `feature/terminal-progress-ui` |
| Base branch | `develop/v2.2` (`fb80155`) |
| Worktree path | `C:\Users\ZHmso\AppData\Local\Temp\codex-genshin-worktrees-20260615223227\get_genshin_wiki-terminal-progress-ui` |
| Created at | `2026-06-15` |

## Goal

Add a lightweight terminal display for `python main.py all` and `python main.py all <entity>` that shows:

- the current executing item
- completed items
- execution progress
- pending items

The UI must stay lightweight, avoid complex terminal libraries, and preserve existing machine-readable command output.

## Implementation Scope

- [ ] Design a progress event model that all `all` runners can emit.
- [ ] Add a lightweight terminal renderer that redraws a compact dashboard on interactive terminals.
- [ ] Keep final JSON output on `stdout` and progress UI on `stderr`.
- [ ] Instrument shared loops such as `_run_all_title_pipeline()` and top-level `handle_all_everything()`.
- [ ] Cover special runners (`characters`, `event-quests`, `chronicles`, `north-library`, `archon-quests`, `character-quests`) with the same progress model.
- [ ] Show per-entity and top-level progress counts, current phase, current title, recent completions, and a preview of remaining items.
- [ ] Add safe fallback behavior for non-interactive shells, redirected output, and terminals without ANSI support.
- [ ] Document the behavior and any control flags.

## Acceptance Criteria

- `python main.py all` shows live top-level progress without breaking final JSON output.
- `python main.py all weapons` shows current item, completed items, total progress, and pending titles.
- Non-TTY use remains script-friendly and does not receive dashboard noise on `stdout`.
- Failures and skipped/resumed items are visible in the progress output.
- The implementation does not add `rich`, `textual`, or other heavy UI dependencies.

## Technical Constraints

- Prefer stdlib-only rendering with ANSI escape sequences and line rewriting.
- Refresh only on state changes or coarse time intervals.
- Keep the renderer isolated from crawl/parse business logic.
- Preserve existing command signatures unless a minimal opt-in or opt-out flag is justified.

## Cross-Branch Notes

- Independent from `feature/llm-data-format`.
- Expected touch points: `get_genshin_wiki/cli.py`, small helper module(s), docs, and tests.
- Merge order is flexible because this branch does not depend on the parsed JSON redesign.
