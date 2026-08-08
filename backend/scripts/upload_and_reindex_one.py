#!/usr/bin/env python3
"""
End-to-end Docling smoke test for the current RAG environment.

Pipeline:
  1. pick a local file (PDF / Word / PPT / Excel / image / HTML)
  2. pick the first KB (or use --kb-id) that has at least one existing doc
  3. copy the file into KB storage, create a Document record
  4. enqueue + drain a REINDEX job (which will run the real Docling parser)
  5. print: parser_version, chunk count, page/modality/section_path samples

Usage:
  E:/xaizai/wendaxitog/backend/.venv/Scripts/python.exe backend/scripts/upload_and_reindex_one.py --file <path> [--kb-id <id>]

Notes:
  - First time Docling sees a PDF it downloads layout/table models from
    HuggingFace (~tens of MB, cached under ~/.cache/huggingface). Needs network.
  - Does NOT require the uvicorn backend to be running — it drives the
    indexer pipeline directly via the same service layer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 中文 Windows 上 torch inductor 读取 CUDA kernel 模板文件时会用系统 GBK 编码去
# 解码 UTF-8 内容，导致 'gbk' codec can't decode byte ... 错误，使 Docling 的
# 版面模型加载失败（进而解析被静默降级成占位块）。修复：启用 Python UTF-8 模式
# 并禁用 torch.compile（让其变 no-op，彻底绕开 inductor 路径）。这两个必须在
# 解释器启动前设置，所以若当前进程未满足则重新以正确环境 exec 自身。
if getattr(sys.flags, "utf8_mode", 0) == 0 or not os.environ.get("TORCH_COMPILE_DISABLE"):
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ["TORCH_COMPILE_DISABLE"] = "1"
    os.execv(sys.executable, [sys.executable, "-X", "utf8", sys.argv[0], *sys.argv[1:]])

import argparse
import asyncio
import mimetypes
import shutil

# Make the backend package importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.common import DocStatus, JobType
from app.models.document import Document, DocumentVersion
from app.models.knowledge_base import KnowledgeBase
from app.models.chunk import Chunk
from app.services.parsing import parser_version_for
from app.services.parsing_docling import docling_available
from app.services.storage import _ALLOWED_EXT
from app.services.task_system import enqueue_job, run_worker_once
from app.services.worker_handlers import HANDLERS
from app.utils.hash import sha256_file
from app.utils.id import doc_id


def _guess_mime(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


async def _pick_kb(session, kb_id: str | None) -> KnowledgeBase:
    if kb_id:
        kb = (
            await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
        ).scalar_one_or_none()
        if kb is None:
            raise SystemExit(f"[ERR] kb-id {kb_id} not found")
        return kb
    kb = (
        await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id.in_(
                    select(Document.kb_id).where(Document.storage_path != "")
                )
            )
        )
    ).scalars().first()
    if kb is None:
        raise SystemExit("[ERR] no KB with stored documents found; create one first")
    return kb


async def main() -> int:
    ap = argparse.ArgumentParser(description="Upload one file and reindex it via Docling")
    ap.add_argument(
        "file_pos",
        nargs="?",
        default=None,
        metavar="FILE",
        help="local file path to import (positional)",
    )
    ap.add_argument("--file", dest="file_flag", default=None,
                    metavar="FILE", help="alias for positional file")
    ap.add_argument("--kb-id", default=None, help="target KB id (default: first KB)")
    ap.add_argument(
        "--download-sample",
        action="store_true",
        help="ignore --file and fetch a known PDF from docling repo, save under backend/sample.pdf, then upload it",
    )
    args = ap.parse_args()

    if args.download_sample:
        import urllib.request

        sample_url = "https://raw.githubusercontent.com/DS4SD/docling/main/tests/data/2206.01062.pdf"
        sample_path = Path(__file__).resolve().parent.parent / "sample.pdf"
        print(f"Downloading {sample_url} -> {sample_path}")
        with urllib.request.urlopen(sample_url, timeout=60) as resp:
            sample_path.write_bytes(resp.read())
        print(f"  saved {sample_path.stat().st_size} bytes")
        args.file_flag = str(sample_path)

    file_path = args.file_flag or args.file_pos
    if not file_path:
        ap.error("file path required (or use --download-sample)")
    src = Path(file_path).expanduser().resolve()
    if not src.is_file():
        print(f"[ERR] file not found: {src}")
        return 1
    ext = src.suffix.lower()
    if ext not in _ALLOWED_EXT:
        print(f"[ERR] unsupported extension {ext}; allowed: {sorted(_ALLOWED_EXT)}")
        return 1
    if ext in {".md", ".markdown", ".txt"}:
        print(
            "[WARN] md/txt always uses the markdown parser (md-0.1); "
            "this script is meant for PDF/Word/PPT/Excel/image/HTML to verify Docling."
        )

    print(f"file      : {src}")
    print(f"ext       : {ext}")
    print(f"docling_available: {docling_available()}")
    print(f"expected parser_version: {parser_version_for(ext)}")
    print()

    if not docling_available() and ext not in {".md", ".markdown", ".txt"}:
        print(
            "[WARN] docling is not importable; the parser will fall back to legacy placeholder."
        )

    # ---- Smoke test: call Docling directly so any error is visible (parsing.py
    # silently falls back to parse_placeholder on exception, which would otherwise
    # hide the real failure).
    if ext in {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
               ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"} and docling_available():
        from app.services.parsing_docling import convert_document
        print("\n[smoke] directly invoking convert_document() on the source file ...")
        try:
            smoke_specs = convert_document(str(src), ext, enable_ocr=False)
            print(f"  [smoke] ok: {len(smoke_specs)} chunks produced")
            for s in smoke_specs[:3]:
                preview = (s.content or "").replace("\n", " ")[:80]
                print(f"    page={s.page_number} modality={s.modality} sec={s.section_path} | {preview}")
        except Exception as e:  # noqa: BLE001
            import traceback
            print(f"  [smoke] FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()
            print(
                "\n  -> the indexing job below will ALSO fail with the same error and fall back\n"
                "     to a placeholder chunk. Re-run after fixing the underlying issue."
            )

    async with AsyncSessionLocal() as session:
        kb = await _pick_kb(session, args.kb_id)
        print(f"target KB : id={kb.id} name={getattr(kb, 'name', '?')} gen={kb.current_generation}")

        # Copy file into KB storage directory.
        did = doc_id()
        kb_root = settings.kb_storage_path / kb.id
        kb_root.mkdir(parents=True, exist_ok=True)
        doc_dir = kb_root / did
        doc_dir.mkdir(parents=True, exist_ok=True)
        dest = doc_dir / f"original{ext}"
        size = src.stat().st_size
        shutil.copy2(src, dest)
        print(f"stored at : {dest}  ({size} bytes)")

        content_hash = sha256_file(str(dest))
        mime = _guess_mime(src)
        doc = Document(
            id=did, kb_id=kb.id, filename=src.name,
            mime_type=mime, ext=ext, content_hash=content_hash,
            size_bytes=size, status=DocStatus.PENDING,
            storage_path=str(dest),
        )
        session.add(doc)

        job = await enqueue_job(
            session, JobType.REINDEX, kb.id, doc_id=did,
            payload={"storage_path": str(dest), "ext": ext},
        )
        await session.commit()
        print(f"document  : id={did}")
        print(f"job       : id={job.id} type=REINDEX")

    print("\nDraining job queue (worker_id=upload-cli) ...")
    loop_total = 0
    while await run_worker_once("upload-cli", HANDLERS):
        loop_total += 1
        print(f"  worker cycle #{loop_total} finished")

    # Report final state.
    async with AsyncSessionLocal() as session:
        doc_db = (
            await session.execute(select(Document).where(Document.id == did))
        ).scalar_one_or_none()
        if doc_db is None:
            print("[ERR] document vanished after reindex")
            return 1
        print(f"\ndoc status: {doc_db.status} current_version={doc_db.current_version}")

        version_row = (
            await session.execute(
                select(DocumentVersion).where(DocumentVersion.doc_id == did).order_by(
                    DocumentVersion.version.desc()
                ).limit(1)
            )
        ).scalar_one_or_none()
        if version_row is None:
            print("[ERR] no DocumentVersion created; reindex likely failed")
            return 1
        print(
            f"version   : v{version_row.version} parser_version={version_row.parser_version} "
            f"num_pages={version_row.num_pages} size={version_row.size_bytes}"
        )

        chunks = (
            await session.execute(
                select(Chunk).where(Chunk.doc_id == did).order_by(Chunk.chunk_index)
            )
        ).scalars().all()
        print(f"chunks    : {len(chunks)}")
        # Sample up to 8 chunks with key metadata.
        print("\n== sample chunks ==")
        for c in chunks[:8]:
            preview = (c.content or "").replace("\n", " ")[:80]
            sec = " > ".join(c.section_path) if c.section_path else "-"
            print(
                f"  #{c.chunk_index:3d} modality={c.modality:6s} page={c.page_number:3d} "
                f"parser={c.parser_version:12s} sec=[{sec}]"
            )
            print(f"        {preview}")
        if len(chunks) > 8:
            print(f"  ... ({len(chunks) - 8} more)")

        # Aggregate parser_version of new chunks.
        rows = (
            await session.execute(
                select(Chunk.parser_version, func.count(Chunk.id))
                .where(Chunk.doc_id == did)
                .group_by(Chunk.parser_version)
            )
        ).all()
        print("\n== parser_version of new chunks ==")
        for pv, cnt in rows:
            print(f"  {pv or '(NULL)':20s} {cnt:4d}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
