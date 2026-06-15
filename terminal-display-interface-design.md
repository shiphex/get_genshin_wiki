# Terminal Display Interface Design

## Objective

Design a lightweight terminal interface for long-running crawl/parse commands such as:

- `python main.py all`
- `python main.py all weapons`
- `python main.py all characters`

The interface must be information-rich without pulling in complex display libraries.

## Existing Behavior

The current `all` commands build results in Python and print JSON at the end. The shared pipeline and special-case runners already know enough to emit progress events:

- the total entity order is fixed for `python main.py all`
- standard entity handlers iterate a concrete title list
- special handlers iterate explicit entry lists or member titles
- `_run_all_title_pipeline()` is a natural hook for title-level progress

That means the display work should focus on instrumentation and rendering, not on inventing a new execution model.

## Design Requirements

1. `stdout` must remain reserved for final JSON output.
2. Live progress must render on `stderr`.
3. The display must work without `rich`, `textual`, `prompt_toolkit`, or similar libraries.
4. It must degrade cleanly when output is redirected or ANSI is unavailable.
5. The UI must show both top-level entity progress and item-level progress when possible.

## Proposed Architecture

Introduce a small progress abstraction:

```python
class ProgressSink(Protocol):
    def run_started(self, event: RunStarted) -> None: ...
    def item_started(self, event: ItemStarted) -> None: ...
    def item_finished(self, event: ItemFinished) -> None: ...
    def item_failed(self, event: ItemFailed) -> None: ...
    def run_finished(self, event: RunFinished) -> None: ...
```

Concrete implementations:

- `NullProgressSink`: no-op default for tests and non-interactive use
- `TerminalProgressSink`: interactive `stderr` renderer
- optional `LineProgressSink`: one-line log fallback when full redraw is not appropriate

## Renderer Rules

- Detect TTY with `sys.stderr.isatty()`.
- Use `shutil.get_terminal_size()` to cap widths.
- Redraw only the dashboard area, not the whole scrollback.
- Refresh on state changes, plus optional throttling for noisy loops.
- Keep the retained history small, for example the last 5 completed items.

## Display Layout

Suggested layout:

```text
[all] entity 4/17 | item 58/240 | 24.2% | elapsed 00:03:18
Current : weapons :: parse :: 霜结的誓金枝
Done    : [ok] 「渔获」 0.7s | [ok] 薙草之稻光 0.9s | [ok] 西风长枪 0.6s
Pending : next entity artifacts | next items 千岩长枪, 贯月矢, 匣里灭辰
Status  : persist=yes | page_limit=none | warnings=0 | failures=0
```

For single-entity runs, the first line becomes:

```text
[weapons] 58/132 pages | 43.9% | elapsed 00:03:18
```

## Event Semantics

Every item event should carry:

- `entity_id`
- `phase` such as `discover`, `crawl`, `parse`, `persist`
- `title`
- `index`
- `total`
- `started_at`
- `finished_at`
- `status` such as `ok`, `failed`, `skipped`, `resumed`

For `python main.py all`, the renderer should also receive top-level entity events:

- current entity index
- total entities
- completed entity summaries
- pending entity list

## Pending Item Strategy

The UI must show pending items, but it should stay lightweight:

- compute the concrete title queue once per entity when feasible
- show only the next few pending titles, not the entire backlog
- for dynamic discovery flows, show the next known items and keep counts exact once the queue is finalized

## Integration Points

Recommended hook points:

- parser/runner setup in `handle_all_everything()`
- shared title loop in `_run_all_title_pipeline()`
- each special `all` runner before and after `crawl_page`, parse, and persist operations
- summary generation after each entity completes

Avoid mixing terminal rendering code directly into parsing logic. The runner should emit events; the sink should render them.

## Compatibility Rules

- If `stderr` is not a TTY, disable the dashboard automatically.
- If `stdout` is redirected, final JSON behavior must remain unchanged.
- If a future flag is needed, prefer `--progress` and `--no-progress`.
- Keyboard interaction is out of scope.

## Failure Presentation

Failures should be visible immediately:

- current line switches to `failed`
- completed history stores the error state
- final status line includes failure count
- final JSON output remains the source of full machine-readable details

## Acceptance Checklist

- live dashboard appears for interactive `all` runs
- JSON output stays machine-readable on `stdout`
- completed, current, progress, and pending states are all visible
- renderer works in PowerShell without extra dependencies
- non-interactive usage remains clean
