# Feature Spec: LLM-Ready Parsed JSON Format

> This file was generated during worktree setup to guide implementation in this branch.

## Branch Info

| Item | Value |
|------|-------|
| Branch name | `feature/llm-data-format` |
| Base branch | `develop/v2.2` (`fb80155`) |
| Worktree path | `C:\Users\ZHmso\AppData\Local\Temp\codex-genshin-worktrees-20260615223227\get_genshin_wiki-llm-data-format` |
| Created at | `2026-06-15` |

## Goal

Redesign parsed JSON output so one canonical record format can feed:

- pretraining corpora
- SFT / LoRA fine-tuning
- RLHF / RLAIF / PPO / DPO / GRPO preference pipelines
- RAG indexing and chunk retrieval
- downstream analytics without entity-specific adapters

## Implementation Scope

- [ ] Audit current `data/parsed/*` record shapes and list shared vs entity-specific fields.
- [ ] Define a versioned canonical envelope for every parsed record.
- [ ] Replace top-level entity-specific Chinese label keys with normalized ASCII keys while preserving raw extracted fields.
- [ ] Add stable IDs, source provenance, and parser metadata to each record.
- [ ] Add common content blocks such as summary text, sections, attributes, aliases, relationships, and tags.
- [ ] Add chunk-friendly structures and deterministic section IDs for RAG/vector indexing.
- [ ] Define how optional derived training views are attached or generated from the canonical record.
- [ ] Provide a migration plan for existing output namespaces and fixtures.
- [ ] Add tests that cover serialization, required fields, and representative entity fixtures.

## Acceptance Criteria

- Every parsed record includes `schema_version`, `record_id`, `entity_type`, `title`, `source`, `content`, `provenance`, and `quality`.
- Missing scalar values are represented consistently, and collection fields use stable empty arrays/objects instead of ad hoc omission.
- A downstream consumer can build training documents or RAG chunks without reading entity-specific Chinese top-level keys such as `名称`, `类型`, or `故事`.
- The format preserves source fidelity by keeping raw extracted values and source references alongside normalized fields.
- At least one representative fixture for each entity family passes the new schema expectations.

## Technical Constraints

- Do not introduce heavy new dependencies for schema handling or rendering.
- Keep existing crawl/parse entry points usable.
- Preserve UTF-8 JSON output and compatibility with `JsonFileStore`.
- Prefer additive or versioned migration over breaking silent rewrites of existing stored data.

## Cross-Branch Notes

- Independent from `feature/terminal-progress-ui`.
- Likely touch points: parser serializers, model-to-dict output, storage namespace policy, docs, and tests.
- Merge order is flexible because there is no direct dependency on the terminal UI work.
