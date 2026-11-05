"""Deterministic display rules; no template expansion through HTTP or Lua."""
from __future__ import annotations

import html

import mwparserfromhell as mw
from mwparserfromhell.nodes import Comment, Heading, HTMLEntity, Tag, Template, Text, Wikilink, ExternalLink

DISPLAY_TAGS = {"big", "small", "b", "strong", "i", "em", "u", "s", "del", "span", "font", "center", "div", "p", "blockquote", "poem", "ruby", "rb", "sup", "sub", "code", "li", "dd", "dt", "ul", "ol", "dl", "onlyinclude", "includeonly", "noinclude", "nowiki"}
DISPLAY_TEMPLATES = {"颜色", "折叠", "注音", "黑幕", "人物对话", "任务描述", "!", "切换板"}


def display_param(template):
    name = str(template.name).strip()
    choices = {"颜色": ("描述", "内容", "2", "3"), "折叠": ("内容", "2"),
               "折叠框": ("内容", "2"), "注音": ("1",), "黑幕": ("1",), "任务描述": ("1", "描述")}.get(name, ())
    if name.startswith("#tag:") and name.split(":", 1)[1].lower() in DISPLAY_TAGS:
        choices = ("1",)
    for key in choices:
        if template.has(key):
            return template.get(key)
    return None


def display_text(raw: str, *, unknown: list[str] | None = None) -> str:
    parts = []
    for node in mw.parse(raw).nodes:
        if isinstance(node, (Text, HTMLEntity)):
            parts.append(html.unescape(str(node)))
        elif isinstance(node, Comment):
            continue
        elif isinstance(node, Heading):
            parts.append(display_text(str(node.title), unknown=unknown))
        elif isinstance(node, Wikilink):
            title = str(node.title).strip()
            if title.lower().startswith(("file:", "image:", "category:", "文件:", "分类:")):
                continue
            parts.append(display_text(str(node.text if node.text is not None else node.title), unknown=unknown))
        elif isinstance(node, ExternalLink):
            parts.append(display_text(str(node.title), unknown=unknown) if node.title is not None else str(node.url))
        elif isinstance(node, Tag):
            name = str(node.tag).lower()
            if name == "br":
                parts.append("\n")
            elif name in DISPLAY_TAGS:
                parts.append(display_text(str(node.contents), unknown=unknown))
            elif name in {"rt", "rp", "ref", "references", "style", "script"}:
                continue
            else:
                if unknown is not None:
                    unknown.append(str(node))
                parts.append(str(node))
        elif isinstance(node, Template):
            name = str(node.name).strip()
            param = display_param(node)
            if param is not None:
                parts.append(display_text(str(param.value), unknown=unknown))
            elif name == "!":
                parts.append("|")
            elif name == "切换板":
                continue
            elif name in {"图标", "icon"} and node.has("1"):
                parts.append(display_text(str(node.get("1").value), unknown=unknown))
            elif name in {"玩家名", "旅行者名字", "NICKNAME"}:
                parts.append(str(node))
            else:
                if unknown is not None:
                    unknown.append(str(node))
                parts.append(str(node))
        else:
            if unknown is not None:
                unknown.append(str(node))
            parts.append(str(node))
    return "".join(parts).replace("\r\n", "\n").replace("\r", "\n").strip()


def replay_unit(wikitext: str, unit: dict) -> str:
    source = unit["source"]
    raw = omit_source_spans(wikitext[source["start"]:source["end"]], source["start"],
                            unit.get("excluded_spans", []))
    return display_text(raw)


def omit_source_spans(raw: str, start: int, spans: list[dict]) -> str:
    """Remove explicitly accounted-for inline nodes without changing raw data."""
    parts, cursor = [], 0
    for span in sorted(spans, key=lambda item: item["start"]):
        left, right = span["start"] - start, span["end"] - start
        if not 0 <= cursor <= left < right <= len(raw):
            raise ValueError("excluded spans must be non-overlapping and inside the source")
        parts.append(raw[cursor:left])
        cursor = right
    parts.append(raw[cursor:])
    return "".join(parts)


def blackout_nodes(raw: str, start: int):
    """Find blackouts only along visible display paths, preserving exact spans."""
    from .source import nodes_with_spans, tag_contents, template_params

    for node, left, right in nodes_with_spans(raw, start):
        if isinstance(node, Template):
            selected = display_param(node)
            if selected is not None:
                param = next(p for p in reversed(list(template_params(node, left)))
                             if p[0] == str(selected.name).strip())
                if str(node.name).strip() == "黑幕":
                    yield left, right, param
                else:
                    yield from blackout_nodes(param[1], param[2])
        elif isinstance(node, Tag) and str(node.tag).lower() in DISPLAY_TAGS:
            contents, content_start = tag_contents(node, left)
            yield from blackout_nodes(contents, content_start)
        elif isinstance(node, Wikilink):
            title = str(node.title)
            if not title.lower().startswith(("file:", "image:", "category:", "文件:", "分类:")):
                label = str(node.text) if node.text is not None else title
                yield from blackout_nodes(label, left + (3 + len(title) if node.text is not None else 2))


def display_projection(raw: str, start: int):
    """Positive evidence for visible leaves, separate from the replay envelope."""
    from .source import nodes_with_spans, tag_contents, template_params

    visible, metadata, unsupported = [], [], []

    def walk(fragment, base):
        for node, left, right in nodes_with_spans(fragment, base):
            if isinstance(node, (Text, HTMLEntity)):
                visible.append((left, right))
            elif isinstance(node, Comment):
                metadata.append((left, right))
            elif isinstance(node, Tag):
                name = str(node.tag).lower()
                if name in DISPLAY_TAGS:
                    contents, content_start = tag_contents(node, left)
                    walk(contents, content_start)
                else:
                    metadata.append((left, right))
            elif isinstance(node, Wikilink):
                title = str(node.title)
                if title.lower().startswith(("file:", "image:", "category:", "文件:", "分类:")):
                    metadata.append((left, right))
                elif node.text is None:
                    walk(title, left + 2)
                else:
                    metadata.append((left + 2, left + 2 + len(title)))
                    walk(str(node.text), left + 3 + len(title))
            elif isinstance(node, ExternalLink):
                if node.title is not None:
                    label = str(node.title)
                    label_start = right - (1 if node.brackets else 0) - len(label)
                    walk(label, label_start)
                else:
                    visible.append((left, right))
            elif isinstance(node, Template):
                name = str(node.name).strip()
                selected = display_param(node)
                if selected is None and name in {"图标", "icon"} and node.has("1"):
                    selected = node.get("1")
                if name in {"玩家名", "旅行者名字", "NICKNAME"}:
                    visible.append((left, right))
                    continue
                if name in {"!", "切换板"}:
                    metadata.append((left, right))
                    continue
                known = {"颜色": {"1"}, "注音": {"2"}, "图标": {"2", "3"}, "icon": {"2", "3"},
                         "任务描述": set(), "黑幕": set()}.get(name, set())
                if name.startswith("#tag:"):
                    known = {"style", "class", "id", "color", "size", "align", "width", "height"}
                for param, (key, value, value_start, value_end) in zip(node.params, template_params(node, left)):
                    if param is selected:
                        walk(value, value_start)
                    elif key in known:
                        metadata.append((value_start, value_end))
                    else:
                        unsupported.append((value_start, value_end, name, key))
            elif isinstance(node, Heading):
                walk(str(node.title), left + node.level)
            else:
                unsupported.append((left, right, type(node).__name__, ""))

    walk(raw, start)
    return visible, metadata, unsupported
