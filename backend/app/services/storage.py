"""Knowledge-base file storage (PLAN: 原文件保存在知识库专属目录).

Stores original uploads under ``<kb_storage_dir>/<kb_id>/<doc_id>/<filename>`` and
performs MIME + extension double validation (PLAN 3.Offline safety test: 伪造 MIME).
"""
from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.utils.id import doc_id

# Allowed extensions -> expected MIME prefixes (kept permissive for the scaffold).
_ALLOWED_EXT = {
    ".pdf": {"application/pdf"},
    ".md": {"text/markdown", "text/plain"},
    ".markdown": {"text/markdown", "text/plain"},
    ".txt": {"text/plain"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".html": {"text/html"},
    ".htm": {"text/html"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".bmp": {"image/bmp"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
}


def _validate(filename: str, declared_mime: str) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise ValueError(f"Unsupported extension: {ext}")
    # Double check: declared MIME must match the extension's expected family.
    allowed = _ALLOWED_EXT[ext]
    if not any(declared_mime.startswith(a.split("/")[0]) or declared_mime in allowed for a in allowed):
        # Allow empty/unknown declared mime only if extension is unambiguous.
        if declared_mime and declared_mime not in allowed:
            raise ValueError(f"MIME {declared_mime} does not match extension {ext}")
    return ext, declared_mime or mimetypes.guess_type(filename)[0] or "application/octet-stream"


async def save_upload(kb_id: str, file: UploadFile) -> dict:
    """Validate + persist an upload; return metadata dict (no content in DB)."""
    filename = file.filename or "upload"
    declared_mime = file.content_type or ""
    ext, mime = _validate(filename, declared_mime)

    did = doc_id()
    kb_root = settings.kb_storage_path / kb_id
    kb_root.mkdir(parents=True, exist_ok=True)
    doc_dir = kb_root / did
    doc_dir.mkdir(parents=True, exist_ok=True)

    dest = doc_dir / f"original{ext}"
    size = 0
    with dest.open("wb") as out:
        # Stream in chunks to respect max_file_bytes.
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_file_bytes:
                shutil.rmtree(doc_dir, ignore_errors=True)
                raise ValueError(
                    f"File exceeds max size {settings.max_file_bytes} bytes"
                )
            out.write(chunk)

    return {
        "doc_id": did,
        "storage_path": str(dest),
        "filename": filename,
        "ext": ext,
        "mime_type": mime,
        "size_bytes": size,
    }
