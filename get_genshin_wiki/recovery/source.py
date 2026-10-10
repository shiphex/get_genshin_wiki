"""Read-only page identities and offsets in the original decoded WikiText."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cached_property
from typing import Any

import mwparserfromhell as mw


def stable_id(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourcePage:
    title: str
    page_id: int | str | None
    raw_file: str
    text: str
    revision_id: int | str | None
    missing: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any], raw_file: str = "") -> "SourcePage":
        pages = payload.get("query", {}).get("pages", {})
        if len(pages) != 1:
            raise ValueError("recovery requires exactly one page per payload")
        page = next(iter(pages.values()))
        revisions = page.get("revisions", [])
        revision = revisions[0] if revisions else {}
        text = revision.get("slots", {}).get("main", {}).get("*", revision.get("*", ""))
        if not isinstance(text, str):
            raise ValueError("WikiText must be a decoded string")
        return cls(page.get("title", ""), page.get("pageid"), raw_file, text,
                   revision.get("revid"), "missing" in page or not revisions)

    @property
    def identity(self) -> tuple[Any, ...]:
        return self.page_id, self.title, self.raw_file

    @cached_property
    def wikitext_hash(self):
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def source(self, start: int | None = None, end: int | None = None) -> dict[str, Any]:
        result = {"page_id": self.page_id, "page_title": self.title, "raw_file": self.raw_file,
                  "wikitext_sha256": self.wikitext_hash,
                  "revision_id": self.revision_id}
        if start is not None:
            if end is None or not 0 <= start <= end <= len(self.text):
                raise ValueError("source span outside decoded WikiText")
            result.update(start=start, end=end)
        return result


def nodes_with_spans(raw: str, start: int = 0):
    code = mw.parse(raw)
    if str(code) != raw:
        raise ValueError("WikiText AST did not preserve the source")
    cursor = start
    for node in code.nodes:
        serialized = str(node)
        yield node, cursor, cursor + len(serialized)
        cursor += len(serialized)


def template_params(template, start: int):
    """Locate parameters by exact serialization, never by a value search."""
    cursor = start + 2 + len(str(template.name))
    for param in template.params:
        value_start = cursor + 1
        if param.showkey:
            value_start += len(str(param.name)) + 1
        raw = str(param.value)
        yield str(param.name).strip(), raw, value_start, value_start + len(raw)
        cursor += 1 + len(str(param))


def tag_contents(tag, start: int) -> tuple[str, int]:
    raw = str(tag)
    if tag.wiki_markup:
        opening = tag.wiki_markup + "".join(str(attr) for attr in tag.attributes) + (tag.padding or "") + (tag.wiki_style_separator or "")
    else:
        opening = ("</" if tag.invalid else "<") + str(tag.tag) + "".join(str(attr) for attr in tag.attributes) + tag.padding
        opening += ">" if not tag.self_closing or tag.implicit else "/>"
    offset = len(opening)
    contents = str(tag.contents)
    if raw[offset:offset + len(contents)] != contents:
        raise ValueError("tag content span does not match source")
    return contents, start + offset
