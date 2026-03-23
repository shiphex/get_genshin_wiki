"""Text cleaning utilities for MediaWiki content."""

import re
from typing import Set


class TextCleaner:
    """Cleaner for MediaWiki text content."""

    def __init__(self):
        """Initialize text cleaner."""
        # Patterns for noise removal
        self._footnote_pattern = re.compile(
            r'<ref[^>]*>.*?</ref>',
            re.DOTALL | re.IGNORECASE
        )
        self._ref_pattern = re.compile(
            r'\[?\[?参考文献?\]\]?',
            re.IGNORECASE
        )
        self._template_noise = re.compile(
            r'\{\{[^{}]*\}\}',
            re.DOTALL
        )
        self._multiple_newlines = re.compile(r'\n{3,}')
        self._multiple_spaces = re.compile(r' {2,}')
        self._repeated_punctuation = re.compile(r'([。！？；：,.!?;:])\1+')

    def clean(self, text: str) -> str:
        """
        Clean text content.

        Args:
            text: Raw text content

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove HTML tags
        text = self._remove_html_tags(text)

        # Remove footnotes/references
        text = self._remove_footnotes(text)

        # Remove template noise but keep some structure
        text = self._clean_templates(text)

        # Remove wiki markup
        text = self._remove_wiki_markup(text)

        # Normalize whitespace
        text = self._normalize_whitespace(text)

        # Clean punctuation
        text = self._clean_punctuation(text)

        return text.strip()

    def _remove_html_tags(self, text: str) -> str:
        """Remove HTML tags."""
        # Keep some useful tags
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        return text

    def _remove_footnotes(self, text: str) -> str:
        """Remove footnote references."""
        text = self._footnote_pattern.sub('', text)
        # Remove reference numbers like [1], [2], etc.
        text = re.sub(r'\[\d+\]', '', text)
        # Remove citation markers
        text = self._ref_pattern.sub('', text)
        return text

    def _clean_templates(self, text: str) -> str:
        """Clean template markup."""
        # Remove certain noisy templates
        noisy_templates = [
            '引用',
            'Citation',
            'Refbegin',
            'Refend',
            'references',
            '参考文献',
        ]
        for tmpl in noisy_templates:
            pattern = r'\{\{' + tmpl + r'[\s\S]*?\}\}'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Replace infobox and similar with markers
        infobox_pattern = r'\{\{(?:角色|NPC|敌人|Infobox|信息框)[^\}]*\}\}'
        text = re.sub(infobox_pattern, '', text, flags=re.IGNORECASE)

        return text

    def _remove_wiki_markup(self, text: str) -> str:
        """Remove wiki markup."""
        # Remove internal links but keep text
        text = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', text)
        text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)

        # Remove external links
        text = re.sub(r'\[https?://[^\s\]]+\s*([^\]]*)\]', r'\1', text)

        # Remove headings markers
        text = re.sub(r'={2,6}', '', text)

        # Remove bold/italic
        text = re.sub(r"'''", '', text)
        text = re.sub(r"''", '', text)

        # Remove magic words
        magic_words = ['__NOTOC__', '__TOC__', '__FORCETOC__', '__NOEDITSECTION__']
        for word in magic_words:
            text = text.replace(word, '')

        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace."""
        # Replace multiple newlines
        text = self._multiple_newlines.sub('\n\n', text)
        # Replace multiple spaces
        text = self._multiple_spaces.sub(' ', text)
        # Remove leading/trailing whitespace per line
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
        return text

    def _clean_punctuation(self, text: str) -> str:
        """Clean punctuation."""
        # Remove repeated punctuation
        text = self._repeated_punctuation.sub(r'\1', text)
        # Clean up spacing around punctuation
        text = re.sub(r'\s*([，。！？；：,.!?;:])\s*', r'\1', text)
        return text

    def remove_duplicates(self, items: list) -> list:
        """
        Remove duplicate items while preserving order.

        Args:
            items: List of items

        Returns:
            Deduplicated list
        """
        seen: Set[str] = set()
        result = []
        for item in items:
            normalized = item.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                result.append(item)
        return result

    def normalize_categories(self, categories: list) -> list:
        """
        Normalize category names.

        Args:
            categories: List of category names

        Returns:
            Normalized categories
        """
        normalized = []
        for cat in categories:
            # Remove prefix
            cat = re.sub(r'^Category:', '', cat, flags=re.IGNORECASE)
            # Strip whitespace
            cat = cat.strip()
            if cat:
                normalized.append(cat)
        return self.remove_duplicates(normalized)

    def normalize_links(self, links: list) -> list:
        """
        Normalize internal links.

        Args:
            links: List of link titles

        Returns:
            Normalized links
        """
        normalized = []
        for link in links:
            # Remove anchor
            link = link.split('#')[0]
            # Strip whitespace
            link = link.strip()
            if link and not link.startswith(':'):
                normalized.append(link)
        return self.remove_duplicates(normalized)
