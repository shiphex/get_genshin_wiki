# LLM and RAG Parsed JSON Format Requirements

## Problem Summary

Current parsed records are useful for human inspection, but they are not a strong canonical interface for LLM training or retrieval workflows. A sample weapon record uses human-facing Chinese top-level keys such as `名称`, `类型`, `介绍`, and `故事`. That makes downstream use possible, but brittle:

- field names differ by entity
- provenance is incomplete
- missing values are not normalized
- chunking boundaries are implicit
- preference or SFT datasets have no stable record anchors

The new format should define one primary machine-oriented schema that still preserves the original extracted content.

## Design Principles

1. One canonical record first, derived datasets second.
2. Raw fidelity must be preserved.
3. Top-level keys must be ASCII `snake_case`.
4. Stable IDs must be deterministic across reruns.
5. The schema must support both whole-document and chunk-level consumption.
6. Task-specific training examples should reference canonical records instead of replacing them.

## Required Top-Level Shape

```json
{
  "schema_version": "llm_record/v1",
  "record_id": "weapon:yu_huo",
  "entity_type": "weapon",
  "title": {
    "default": "渔获",
    "locale": "zh-CN",
    "aliases": []
  },
  "source": {},
  "content": {},
  "relationships": [],
  "rag": {},
  "provenance": {},
  "quality": {},
  "raw_fields": {}
}
```

## Required Field Rules

### 1. Identity

- `schema_version`: explicit version string for consumers and migrations.
- `record_id`: deterministic ID derived from `entity_type` plus a stable normalized title or source page ID.
- `entity_type`: one of the repo's parsed entity families such as `weapon`, `character`, `monster`, `archon_quest`.

### 2. Title and Locale

- `title.default`: original display title.
- `title.locale`: language tag such as `zh-CN`.
- `title.aliases`: always present as an array, even when empty.

### 3. Source

`source` must include enough information to trace every parsed record back to its wiki origin:

- `site`
- `page_title`
- `page_id` when available
- `page_url`
- `revision_id` and `revision_timestamp` when available
- `fetched_at`
- `parsed_at`
- `parser_name`
- `source_namespace`
- `source_path` when persisted locally

### 4. Content

`content` must expose both human-readable and machine-usable forms:

- `summary`: short normalized overview or `null`
- `document_text`: full plain-text canonical document for pretraining and embedding
- `sections`: ordered array of section objects
- `attributes`: ordered array of normalized key/value facts
- `lists`: optional named list blocks for repeated data
- `tags`: normalized string tags

Section objects must look like:

```json
{
  "section_id": "story",
  "title": "Story",
  "order": 3,
  "text": "Plain text content...",
  "source_labels": ["故事"]
}
```

Attribute objects must look like:

```json
{
  "key": "weapon_type",
  "label": "Type",
  "value": "polearm",
  "display_value": "长柄武器",
  "value_type": "string"
}
```

### 5. Relationships

`relationships` must be an array of typed edges so downstream systems can link entities without custom parsers. Example relation types:

- `uses_material`
- `belongs_to_region`
- `mentions_character`
- `part_of_series`
- `has_voice_page`

Each relation should carry:

- `relation_type`
- `target_type`
- `target_title`
- `target_record_id` when known
- `evidence_section_id` when applicable

### 6. RAG-Specific Requirements

`rag` must include a chunk-ready representation:

- `chunks`: always present as an array
- each chunk has `chunk_id`, `section_id`, `text`, `token_estimate`, `order`, and searchable metadata
- chunks must be deterministic from the canonical record so re-indexing does not break references

Example:

```json
{
  "chunk_id": "weapon:yu_huo:story:0",
  "section_id": "story",
  "order": 0,
  "text": "Story text...",
  "token_estimate": 180,
  "metadata": {
    "entity_type": "weapon",
    "title": "渔获"
  }
}
```

### 7. Provenance and Quality

`provenance` should capture how the record was built:

- `raw_payload_available`
- `voice_payload_used`
- `related_event_payload_used`
- `normalization_steps`
- `warnings`

`quality` should capture output confidence:

- `completeness_score`
- `missing_required_fields`
- `parse_warnings`
- `manual_review_recommended`

## Missing Data Policy

- Missing scalars use `null`.
- Missing collections use empty arrays or empty objects, never empty strings.
- Unknown booleans use `null`, not `false`.
- Do not overload `N/A` or localized placeholder text as real values.

## Training-Dataset Requirements

The canonical parsed record should not try to hard-code every training format directly. Instead:

- pretraining uses `content.document_text`
- SFT can derive prompt/answer pairs from `sections`, `attributes`, and `relationships`
- RLHF, RLAIF, PPO, DPO, and GRPO datasets should reference `record_id`, `section_id`, and chunk IDs so annotations remain stable
- LoRA fine-tuning uses the same canonical source as SFT

Optional derived views may be attached under a separate namespace such as `training_views`, but they must not replace the canonical record.

## Backward Compatibility

- Keep raw extracted fields under `raw_fields`.
- Prefer a versioned output namespace or a dual-write period instead of silently changing the current files in place.
- Existing consumers should have a clear migration path from localized label keys to normalized keys.

## Minimum Success Definition

The format is acceptable only if a downstream consumer can:

1. read any entity with the same top-level schema
2. reconstruct the original extracted labels from `raw_fields`
3. build chunked RAG documents without entity-specific parsing logic
4. attach later SFT or preference annotations using stable IDs
