"""Shared markdown detection utilities."""

import re
from typing import List, Pattern

_MARKDOWN_PATTERNS: List[Pattern] = [
    re.compile(r"\*\*.*\*\*"),        # bold
    re.compile(r"\*.*\*"),            # italic
    re.compile(r"~~.*~~"),           # strikethrough
    re.compile(r"\[.*\]\(.*\)"),     # links
    re.compile(r"`.*`"),             # inline code
    re.compile(r"^#{1,6}\s", re.MULTILINE),  # headers
    re.compile(r"^>\s", re.MULTILINE),       # blockquote
    re.compile(r"^\s*[-*+]\s", re.MULTILINE), # lists
]


def has_markdown(text: str) -> bool:
    """Check if text contains markdown formatting.

    Args:
        text: Input text to check.

    Returns:
        True if any markdown pattern is found.
    """
    return any(p.search(text) for p in _MARKDOWN_PATTERNS)


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text.

    Args:
        text: Input text with markdown.

    Returns:
        Plain text with markdown symbols removed.
    """
    result = text
    result = re.sub(r"\*\*(.+?)\*\*", r"\1", result)
    result = re.sub(r"\*(.+?)\*", r"\1", result)
    result = re.sub(r"~~(.+?)~~", r"\1", result)
    result = re.sub(r"`(.+?)`", r"\1", result)
    result = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", result)
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)
    result = re.sub(r"^>\s+", "", result, flags=re.MULTILINE)
    return result.strip()
