"""Independent lexical inventory and coverage accounting.

This module never calls the semantic extractor or its display renderer. It walks
the original AST independently and reconciles Chinese character positions with
exported source ranges and explicit disposition records.
"""
from __future__ import annotations

import bisect
import collections
import re

import mwparserfromhell as mw
from mwparserfromhell.nodes import Comment, Heading, Tag, Template, Text, Wikilink

from .source import SourcePage, stable_id

CHINESE = re.compile(r"[\u3400-\u9fff]")


def lexical_candidates(page: SourcePage):
    candidates = []

    def add(raw, start, role, context):
        for match in re.finditer(r"[^\r\n]+", raw):
            part = match.group()
            if CHINESE.search(part):
                left = start + match.start()
                candidates.append({"candidate_id": stable_id("candidate", page.identity, left, left + len(part), role),
                                   "text": part, "role": role, "context": context,
                                   "source": page.source(left, left + len(part))})

    def walk(raw, offset, context, role="text"):
        cursor = offset
        parsed = mw.parse(raw)
        if str(parsed) != raw:
            raise ValueError("inventory AST does not preserve original source")
        for node in parsed.nodes:
            serialized = str(node)
            if isinstance(node, Text):
                add(serialized, cursor, role, context)
            elif isinstance(node, Comment):
                add(serialized, cursor, "comment", context)
            elif isinstance(node, Heading):
                walk(str(node.title), cursor + node.level, context + [{"heading": str(node.title)}], "heading")
            elif isinstance(node, Template):
                name = str(node.name)
                add(name, cursor + 2, "template_name", context)
                param_cursor = cursor + 2 + len(name)
                for param in node.params:
                    value_offset = param_cursor + 1
                    if param.showkey:
                        add(str(param.name), value_offset, "parameter_name", context)
                        value_offset += len(str(param.name)) + 1
                    walk(str(param.value), value_offset,
                         context + [{"template": name.strip(), "parameter": str(param.name).strip()}])
                    param_cursor += 1 + len(str(param))
            elif isinstance(node, Tag):
                if node.wiki_markup:
                    tail = node.closing_wiki_markup or ""
                    opening_size = len(serialized) - len(str(node.contents)) - len(tail) if not node.self_closing else len(serialized)
                else:
                    tail = "</" + str(node.closing_tag) + ">"
                    opening_size = len(serialized) - len(str(node.contents)) - len(tail) if not node.self_closing else len(serialized)
                contents = str(node.contents)
                if serialized[opening_size:opening_size + len(contents)] != contents:
                    add(serialized, cursor, "unsupported_markup", context)
                else:
                    name = str(node.tag).lower()
                    child_role = "style" if name in {"style", "script"} else "reference" if name in {"ref", "references"} else role
                    walk(contents, cursor + opening_size, context + [{"tag": name}], child_role)
            elif isinstance(node, Wikilink):
                title = str(node.title)
                namespace = title.split(":", 1)[0].lower() if ":" in title else ""
                if node.text is None and namespace not in {"file", "image", "文件", "category", "分类"}:
                    walk(title, cursor + 2, context, role)
                else:
                    add(title, cursor + 2, "media" if namespace in {"file", "image", "文件"} else "link_target", context)
                if node.text is not None:
                    walk(str(node.text), cursor + 3 + len(title), context, "media_caption" if namespace in {"file", "image", "文件"} else role)
            else:
                add(serialized, cursor, "unsupported_markup", context)
            cursor += len(serialized)

    walk(page.text, 0, [])
    return candidates


def disposition_segments(regions):
    priority = {"metadata": 1, "non_story": 2, "unsupported": 3, "needs_source": 4, "exported": 5}
    events = collections.defaultdict(list)
    for region in regions:
        source = region["source"]
        if source["start"] < source["end"]:
            events[source["start"]].append((region["disposition"], 1))
            events[source["end"]].append((region["disposition"], -1))
    counts = collections.Counter()
    starts, states = [], []
    for position in sorted(events):
        for disposition, increment in events[position]:
            counts[disposition] += increment
        starts.append(position)
        active = [d for d, count in counts.items() if count > 0]
        states.append(max(active, key=priority.get) if active else "unsupported")
    return starts, states


def audit_page(page: SourcePage, regions: list[dict], units: list[dict]):
    ranges = list(regions)
    for unit in units:
        ranges.append({"source": unit["source"], "disposition": "exported"})
        if unit.get("speaker_source"):
            ranges.append({"source": unit["speaker_source"], "disposition": "metadata"})
    starts, states = disposition_segments(ranges)
    results = []
    for candidate in lexical_candidates(page):
        role = candidate["role"]
        intrinsic = None
        reason = "source_range_reconciliation"
        if role in {"template_name", "parameter_name", "heading", "link_target"}:
            intrinsic, reason = "metadata", "source_structure"
        elif role in {"comment", "style", "reference"}:
            intrinsic, reason = "non_story", "wiki_annotation_or_style"
        elif role in {"media", "media_caption"}:
            intrinsic, reason = "needs_source", "media_text_not_in_snapshot"
        elif any(re.fullmatch(r"语音(?:内容|文件)(?:日语|英语|韩语)", c.get("parameter", "")) for c in candidate["context"]):
            intrinsic, reason = "non_story", "other_language_voice_field"
        counts = collections.Counter()
        for match in CHINESE.finditer(candidate["text"]):
            index = bisect.bisect_right(starts, candidate["source"]["start"] + match.start()) - 1
            counts[intrinsic or (states[index] if index >= 0 else "unsupported")] += 1
        if counts["needs_source"]:
            disposition = "needs_source"
        elif counts["unsupported"]:
            disposition = "unsupported"
        elif counts["exported"]:
            disposition = "exported"
        elif counts["non_story"]:
            disposition = "non_story"
        else:
            disposition = "metadata"
        candidate.update(disposition=disposition, reason=reason, chinese_character_counts=dict(counts))
        results.append(candidate)
    return results
