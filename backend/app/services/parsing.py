"""Lightweight document parsing / chunking (PLAN 2.Offline stub).

Production parsing uses Docling + OCR/VLM (deferred). For the scaffold:

  * ``.md / .markdown / .txt`` -> real heading-aware structured chunking with
    section paths, page_number=0, atomic code/table blocks, ~350–700 token
    target and ~80 token overlap.
  * ``.pdf / .png / .jpg`` -> a single placeholder chunk noting that Docling/OCR
    integration is pending, so retrieval still has *something* to operate on.

Every produced chunk carries: content, section_path, page_number, modality,
token_estimate. This matches the Chunk metadata contract in the models.
"""
from __future__ import annotations

import re

from app.services.parsing_types import ChunkSpec, _split_overlap


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_FENCE_RE = re.compile(r"```")


def parse_markdown(text: str) -> list[ChunkSpec]:
    """Heading-aware chunking that keeps code fences atomic."""
    chunks: list[ChunkSpec] = []
    lines = text.splitlines()
    section_stack: list[tuple[int, str]] = []
    buf: list[str] = []
    in_fence = False
    cur_path: list[str] = []

    def flush(path: list[str]):
        joined = "\n".join(buf).strip()
        if not joined:
            return
        for piece in _split_overlap(joined):
            chunks.append(ChunkSpec(content=piece, section_path=list(path), page_number=0, modality="text"))

    i = 0
    while i < len(lines):
        line = lines[i]
        fence_hit = _FENCE_RE.match(line.strip())
        if fence_hit:
            in_fence = not in_fence
            buf.append(line)
            i += 1
            continue
        if (not in_fence) and (m := _HEADING_RE.match(line)):
            # Heading change -> flush previous section, update stack.
            flush(cur_path)
            buf = []
            level = len(m.group(1))
            title = m.group(2).strip()
            # Keep stack reflecting heading hierarchy.
            section_stack = [(lv, t) for (lv, t) in section_stack if lv < level]
            section_stack.append((level, title))
            cur_path = [t for _, t in section_stack]
            i += 1
            continue
        buf.append(line)
        i += 1
    flush(cur_path)
    return chunks


def parse_placeholder(ext: str) -> list[ChunkSpec]:
    note = {
        ".pdf": "（解析待接入 Docling：版面/表格/图片抽取尚未实现，此处为占位 Chunk。）",
        ".png": "（图片解析待接入 OCR/VLM：图片描述与语义理解尚未实现。）",
        ".jpg": "（图片解析待接入 OCR/VLM：图片描述与语义理解尚未实现。）",
        ".jpeg": "（图片解析待接入 OCR/VLM：图片描述与语义理解尚未实现。）",
    }.get(ext, "（暂不支持的文档类型占位 Chunk。）")
    return [ChunkSpec(content=note, section_path=[], page_number=0, modality="text")]


def parse_document(path: str, ext: str) -> list[ChunkSpec]:
    ext = ext.lower()
    if ext in {".md", ".markdown", ".txt"}:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = ""
        return parse_markdown(text) if text else parse_placeholder(ext)

    # PDF / Office / image -> real Docling extraction when enabled & available.
    if ext in DOCLING_EXTENSIONS and settings.doc_parser in ("auto", "docling"):
        if docling_available():
            try:
                return convert_document(path, ext, enable_ocr=settings.docling_ocr)
            except Exception:  # noqa: BLE001
                # Real parsing failed (e.g. model download blocked) — stay usable.
                return parse_placeholder(ext)
        # docling package not installed -> fall through to legacy placeholder.
    return parse_placeholder(ext)


def parser_version_for(ext: str) -> str:
    """The parser_version string ``parse_document`` will actually use."""
    ext = ext.lower()
    if ext in {".md", ".markdown", ".txt"}:
        return "md-0.1"
    if (
        ext in DOCLING_EXTENSIONS
        and settings.doc_parser in ("auto", "docling")
        and docling_available()
    ):
        return DOC_PARSER_VERSION
    return "legacy-0.1"


from pathlib import Path  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.parsing_docling import (  # noqa: E402
    DOC_PARSER_VERSION,
    DOCLING_EXTENSIONS,
    convert_document,
    docling_available,
)
