"""Conservative, offline release metadata for a page's owning entity.

No version is inferred from dates, prose, rewards, children or related pages.
Evidence offsets refer to the original decoded WikiText, not cleaned text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

import mwparserfromhell as mw


SUBJECT_TEMPLATES = frozenset({
    '角色', '角色资料', '角色信息', '角色/信息', '旅行者/通用',
    '武器图鉴', '武器属性', '武器信息', '武器',
    '圣遗物套装', '圣遗物属性', '圣遗物信息',
    '怪物信息栏', '怪物图鉴', '怪物', '书籍',
    '食物图鉴', '食物图鉴新', '野生生物图鉴', '任务道具',
    '消耗品图鉴', '素材图鉴', '名片', '秘境副本', '任务', '剧情',
})
ALIASES = frozenset({'实装版本', '所属版本', '版本'})
_COMMENT = re.compile(r'<!--.*?-->', re.S)
_VERSION = r'(?:\d+\.\d+|月之[一二三四五六七八九十]+)'
_VALUE = re.compile(_VERSION + r'(?:[、,，/;；]' + _VERSION + r')*')
_RAW_PARAMETER = re.compile(r'(?m)^[ \t]*\|[ \t]*(实装版本|所属版本|版本)[ \t]*=[ \t]*([^\r\n]*)')
_TECHNICAL = re.compile(r'^(?:模板|Template|Widget|模块|Module|分类|Category|帮助|Help|MediaWiki|文件|File):', re.I)


@dataclass
class VersionResolution:
    value: str = ''
    status: str = 'missing'
    evidence: list[dict] = field(default_factory=list)


def normalize_version(raw: str) -> str:
    """Accept an entire version value; never mine numbers from arbitrary text."""
    text = _COMMENT.sub('', raw).strip()
    code = mw.parse(text)
    for template in reversed(code.filter_templates()):
        name = str(template.name).strip().lower()
        positional = [p for p in template.params if str(p.name).strip().isdigit()]
        if name in {'颜色', 'color', '字体'} and len(positional) >= 2:
            code.replace(template, str(positional[-1].value))
        elif name in {'黑幕', '注音'} and positional:
            code.replace(template, str(positional[0].value))
        else:
            return ''
    text = re.sub(r'\s+', '', code.strip_code())
    if not _VALUE.fullmatch(text):
        return ''
    return '、'.join(dict.fromkeys(re.split(r'[、,，/;；]', text)))


def _name(template) -> str:
    return _COMMENT.sub('', str(template.name)).strip().removeprefix('Template:').removeprefix('模板:')


def _spans(text, templates):
    # mwparser's preorder traversal permits nested ranges to overlap.
    cursor = 0
    result = []
    for template in templates:
        raw = str(template)
        start = text.find(raw, cursor)
        if start < 0:
            continue
        result.append((start, start + len(raw), template))
        cursor = start + 2
    return result


def _subjects(code, offset=0):
    """Traverse layout tags, but never descend into another template's values."""
    for node in code.nodes:
        raw = str(node)
        if isinstance(node, mw.nodes.Template):
            if _name(node) in SUBJECT_TEMPLATES:
                yield offset, offset + len(raw), node
        elif isinstance(node, mw.nodes.Tag) and str(node.tag).lower() in {
            'div', 'span', 'onlyinclude', 'includeonly', 'section', 'article', 'center', 'tabber',
        } and node.contents is not None:
            contents = str(node.contents)
            position = raw.find(contents, raw.find('>') + 1) if contents else -1
            if position >= 0:
                yield from _subjects(node.contents, offset + position)
        offset += len(raw)


def extract_version(title: str, wikitext: str) -> VersionResolution:
    """Resolve subject metadata and retain every accepted/rejected candidate."""
    if _TECHNICAL.match(title) or title == '数据组指南':
        return VersionResolution(status='non_entity')
    code = mw.parse(wikitext)
    roots = list(_subjects(code))
    if not roots:
        return VersionResolution()
    evidence = []
    for start, end, template in roots:
        cursor = start + 2 + len(str(template.name))
        for param in template.params:
            param_raw = str(param)
            param_start = wikitext.find(param_raw, cursor, end)
            if param_start < 0:
                continue
            cursor = param_start + len(param_raw)
            if str(param.name).strip() not in ALIASES:
                continue
            value = str(param.value)
            value_start = cursor - len(value)
            evidence.append(dict(template=_name(template), parameter=str(param.name).strip(),
                                 method='template_parameter', start=value_start, end=cursor,
                                 raw=value, normalized=normalize_version(value)))

    # Some cached #arraymap/#ask shapes terminate the owning AST prematurely.
    # Only an orphan parameter in its metadata continuation is eligible. Nested
    # template values and parameters in later sections are never fallback input.
    if len(roots) == 1 and _COMMENT.sub('', str(roots[0][2])).count('{{') > _COMMENT.sub('', str(roots[0][2])).count('}}'):
        start, end, template = roots[0]
        all_spans = _spans(wikitext, code.filter_templates())
        masked = _COMMENT.sub(lambda m: re.sub(r'[^\r\n]', ' ', m.group()), wikitext)
        masked = re.sub(
            r'<(pre|nowiki|code|syntaxhighlight|noinclude)\b[^>]*>.*?</\1\s*>',
            lambda m: re.sub(r'[^\r\n]', ' ', m.group()), masked, flags=re.I | re.S,
        )
        heading = re.search(r'(?m)^\s*={1,6}[^=]', masked[end:])
        boundary = end + heading.start() if heading else len(wikitext)
        continuation = wikitext[end:boundary]
        # A real owning close after the orphan field is required. This rejects
        # unrelated parameter-looking prose after an already complete subject.
        for match in _RAW_PARAMETER.finditer(masked, end, boundary):
            if any(a <= match.start() < b for a, b, _ in all_spans):
                continue
            if not re.search(r'(?m)^[ \t]*}}[ \t]*(?:\r?$|<!--)', wikitext[match.end():boundary]):
                continue
            # The continuation must begin as damaged metadata, rather than prose.
            if not continuation.lstrip().startswith(('|', '}', '（', '(', '、')) and not re.match(
                r'[^\n{}]*\r?\n[ \t]*\|', continuation.lstrip()
            ):
                continue
            raw = wikitext[match.start(2):match.end(2)]
            evidence.append(dict(template=_name(template), parameter=match.group(1),
                                 method='raw_parameter', start=match.start(2), end=match.end(2),
                                 raw=raw, normalized=normalize_version(raw)))

    nonempty = [e for e in evidence if _COMMENT.sub('', e['raw']).strip()]
    values = {e['normalized'] for e in nonempty if e['normalized']}
    if len(values) > 1:
        return VersionResolution(status='conflict', evidence=evidence)
    if any(not e['normalized'] for e in nonempty):
        return VersionResolution(status='invalid', evidence=evidence)
    if values:
        return VersionResolution(value=next(iter(values)), status='resolved', evidence=evidence)
    return VersionResolution(evidence=evidence)
