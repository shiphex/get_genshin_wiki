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
            elif name in {"rt", "ref", "references", "style", "script"}:
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
    return display_text(wikitext[source["start"]:source["end"]])
