"""Shared data types / helpers for document parsing modules.

Lives in its own module so that ``parsing`` and ``parsing_docling`` can both
depend on it without forming a circular import.
"""
from __future__ import annotations

from dataclasses import dataclass


TARGET_TOKENS = 550
OVERLAP_TOKENS = 80
_CHAR_PER_TOKEN = 4


@dataclass
class ChunkSpec:
    """A single indexable chunk produced by any document parser.

    All parsers (``parse_markdown``, ``parse_placeholder``, ``convert_document``)
    return a list of these so downstream indexing can stay parser-agnostic.
    """

    content: str
    section_path: list[str]
    page_number: int
    modality: str


def _est_tokens(text: str) -> int:
    return max(1, len(text) // _CHAR_PER_TOKEN)


def _split_overlap(
    text: str,
    target: int = TARGET_TOKENS,
    overlap: int = OVERLAP_TOKENS,
) -> list[str]:
    """Greedy split into ~target-token pieces with token overlap."""
    target_c = target * _CHAR_PER_TOKEN
    overlap_c = overlap * _CHAR_PER_TOKEN
    pieces: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + target_c)
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end == n:
            break
        start = max(end - overlap_c, start + 1)
    return pieces