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


def resolve_managed_file(storage_path: str) -> Path | None:
    """Return a resolved file only when it remains inside the managed KB root."""
    root = settings.kb_storage_path.resolve()
    try:
        path = Path(storage_path).resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    if path == root or root not in path.parents:
        return None
    return path


def delete_document_storage(storage_path: str) -> bool:
    path = resolve_managed_file(storage_path)
    if path is None:
        return False
    doc_dir = path.parent
    root = settings.kb_storage_path.resolve()
    if doc_dir == root or root not in doc_dir.parents:
        return False
    shutil.rmtree(doc_dir, ignore_errors=False)
    return True


def delete_knowledge_base_storage(kb_id: str) -> bool:
    root = settings.kb_storage_path.resolve()
    target = (root / kb_id).resolve(strict=False)
    if target.parent != root:
        return False
    if target.exists():
        shutil.rmtree(target, ignore_errors=False)
    return True


def copy_source_file(kb_id: str, source: Path, display_name: str) -> dict:
    """Copy one already-authorized source file into managed KB storage.

    The caller is responsible for proving that ``source`` belongs to the configured
    source library. This function still rejects links, validates the extension/MIME,
    streams with a size cap, and only writes under the managed KB root.
    """
    if source.is_symlink():
        raise ValueError("不允许导入符号链接文件")
    try:
        resolved_source = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("源文件不存在或无法读取") from exc
    if not resolved_source.is_file():
        raise ValueError("源路径不是普通文件")

    declared_mime = mimetypes.guess_type(display_name)[0] or ""
    ext, mime = _validate(display_name, declared_mime)
    source_size = resolved_source.stat().st_size
    if source_size > settings.max_file_bytes:
        raise ValueError(f"文件超过 {settings.max_file_bytes} 字节限制")

    did = doc_id()
    kb_root = settings.kb_storage_path / kb_id
    kb_root.mkdir(parents=True, exist_ok=True)
    doc_dir = kb_root / did
    doc_dir.mkdir(parents=True, exist_ok=False)
    dest = doc_dir / f"original{ext}"

    copied = 0
    try:
        with resolved_source.open("rb") as incoming, dest.open("wb") as outgoing:
            while True:
                chunk = incoming.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > settings.max_file_bytes:
                    raise ValueError(f"文件超过 {settings.max_file_bytes} 字节限制")
                outgoing.write(chunk)
        shutil.copystat(resolved_source, dest)
    except Exception:
        shutil.rmtree(doc_dir, ignore_errors=True)
        raise

    return {
        "doc_id": did,
        "storage_path": str(dest),
        "filename": display_name[:512],
        "ext": ext,
        "mime_type": mime,
        "size_bytes": copied,
    }
