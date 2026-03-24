"""Wikitext parser for MediaWiki content."""

import logging
from typing import Any, Dict, List, Optional

try:
    import mwparserfromhell
except ImportError:
    mwparserfromhell = None

from ..schema.models import Infobox

logger = logging.getLogger(__name__)


class WikitextParser:
    """Parser for MediaWiki wikitext content."""

    def __init__(self):
        """Initialize wikitext parser."""
        if mwparserfromhell is None:
            logger.warning("mwparserfromhell not installed, using basic parsing")
        self._infobox_templates = [
            "角色",
            "Character",
            "Infobox",
            "信息框",
            "角色信息",
            "NPC",
            "敌人",
            "生物",
            "物品",
            "装备",
            "武器",
            "圣遗物",
            "食谱",
            "书籍",
            "任务",
            "成就",
        ]

    def parse(self, wikitext: str) -> Dict[str, Any]:
        """
        Parse wikitext and extract structured information.

        Args:
            wikitext: Raw wikitext content

        Returns:
            Dictionary with parsed information
        """
        if not wikitext:
            return self._empty_result()

        if mwparserfromhell is None:
            return self._basic_parse(wikitext)

        try:
            return self._parse_with_mwparser(wikitext)
        except Exception as e:
            logger.warning(f"Failed to parse wikitext: {e}")
            return self._basic_parse(wikitext)

    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure."""
        return {
            "templates": [],
            "links": [],
            "categories": [],
            "text": "",
            "infobox": None,
        }

    def _basic_parse(self, wikitext: str) -> Dict[str, Any]:
        """Basic parsing without mwparserfromhell."""
        templates = self._extract_templates_basic(wikitext)
        links = self._extract_links_basic(wikitext)
        categories = self._extract_categories_basic(wikitext)
        text = wikitext

        infobox = self._extract_infobox_basic(wikitext)

        return {
            "templates": templates,
            "links": links,
            "categories": categories,
            "text": text,
            "infobox": infobox,
        }

    def _parse_with_mwparser(self, wikitext: str) -> Dict[str, Any]:
        """Parse using mwparserfromhell."""
        parsed = mwparserfromhell.parse(wikitext)

        # Extract templates
        templates = [str(t.name).strip() for t in parsed.filter_templates()]

        # Extract internal links
        links = [
            str(link.title).strip()
            for link in parsed.filter_wikilinks()
            if link.title
        ]

        # Extract categories - filter_categories may not exist in newer versions
        try:
            categories = [
                str(cat.title).replace("Category:", "").strip()
                for cat in parsed.filter_categories()
            ]
        except AttributeError:
            # Fallback: extract categories using regex
            categories = self._extract_categories_basic(wikitext)

        # Get plain text
        text = parsed.strip_code()

        # Extract infobox
        infobox = self._extract_infobox(parsed)

        return {
            "templates": templates,
            "links": links,
            "categories": categories,
            "text": text,
            "infobox": infobox,
        }

    def _extract_templates_basic(self, wikitext: str) -> List[str]:
        """Extract template names using basic regex."""
        import re
        pattern = r'\{\{(?!\{)([^{}|]+?)(?:\||\}\})'
        matches = re.findall(pattern, wikitext)
        return [m.strip() for m in matches if m.strip()]

    def _extract_links_basic(self, wikitext: str) -> List[str]:
        """Extract internal links using basic regex."""
        import re
        pattern = r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]'
        matches = re.findall(pattern, wikitext)
        return [m.strip() for m in matches if m and not m.startswith(":")]

    def _extract_categories_basic(self, wikitext: str) -> List[str]:
        """Extract categories using basic regex."""
        import re
        pattern = r'\[\[Category:([^\]]+)\]\]'
        matches = re.findall(pattern, wikitext)
        return [m.strip() for m in matches]

    def _extract_infobox(self, parsed) -> Optional[Infobox]:
        """Extract infobox from parsed wikitext."""
        for template in parsed.filter_templates():
            template_name = str(template.name).strip()

            # Check if it's an infobox template
            is_infobox = any(
                template_name.lower() == infobox.lower()
                or template_name.lower().startswith(infobox.lower())
                for infobox in self._infobox_templates
            )

            if is_infobox:
                # Extract infobox data
                data = {}
                for param in template.params:
                    key = str(param.name).strip()
                    value = str(param.value).strip()
                    data[key] = value

                return Infobox(
                    template_name=template_name,
                    data=data,
                    raw_template=str(template),
                )

        return None

    def _extract_infobox_basic(self, wikitext: str) -> Optional[Infobox]:
        """Extract infobox using basic parsing."""
        import re

        # Find infobox template
        infobox_pattern = r'\{\{(Infobox[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\}'
        matches = re.findall(infobox_pattern, wikitext, re.IGNORECASE | re.DOTALL)

        if not matches:
            # Try simpler pattern
            infobox_pattern = r'\{\{(' + '|'.join(self._infobox_templates) + r')[\s\S]*?\}\}'
            matches = re.findall(infobox_pattern, wikitext, re.IGNORECASE)

        if matches:
            template_text = matches[0]

            # Extract template name
            template_name_match = re.match(r'(\w+)', template_text)
            template_name = template_name_match.group(1) if template_name_match else "Infobox"

            # Extract parameters
            data = {}
            param_pattern = r'\|([^=]+)=([^\n|]+)'
            for match in re.finditer(param_pattern, template_text):
                key = match.group(1).strip()
                value = match.group(2).strip()
                data[key] = value

            return Infobox(
                template_name=template_name,
                data=data,
                raw_template=template_text,
            )

        return None

    def parse_html(self, html: str) -> Dict[str, Any]:
        """
        Parse HTML content.

        Args:
            html: HTML content

        Returns:
            Dictionary with parsed information
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("beautifulsoup4 not installed")
            return {}

        soup = BeautifulSoup(html, "html.parser")

        # Extract text
        text = soup.get_text(separator="\n", strip=True)

        # Extract links
        links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if href.startswith("/") or href.startswith("http"):
                links.append(href)

        # Extract images
        images = []
        for img in soup.find_all("img", src=True):
            images.append(img.get("src", ""))

        return {
            "text": text,
            "links": links,
            "images": images,
            "html": html,
        }
