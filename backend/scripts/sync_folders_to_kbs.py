#!/usr/bin/env python3
"""
批量同步：把「总数据库根目录」下的每个子文件夹，同步为一个知识库。

用法（在 backend 目录下）：
  E:/xaizai/wendaxitog/backend/.venv/Scripts/python.exe \
      E:/xaizai/wendaxitog/backend/scripts/sync_folders_to_kbs.py [--root E:/xaizai/数据库]

规则：
  1. root 的每个「直接子文件夹」= 一个知识库，KB 名 = 文件夹名。
     （例：E:/xaizai/数据库/简历/ -> 知识库「简历」）
  2. 只处理系统支持的扩展名（PDF/Word/PPT/Excel/图片/HTML/md/txt），其余自动忽略。
  3. 增量同步：按「内容哈希」去重——同一 KB 里已存在相同内容的文档自动跳过；
     文件改过内容会重新导入；文件改名不影响去重。
  4. 空文件夹跳过（不建库），放文件后再跑一次即自动建库导入。
  5. 不依赖后端在线：直接驱动 service 层 + 内置 worker 完成解析入库。

安全：脚本只做「复制入库」，不会删除你文件夹里的任何文件。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 中文 Windows 上 torch inductor 读取 CUDA kernel 模板文件时会用系统 GBK 编码去
# 解码 UTF-8 内容，导致 'gbk' codec can't decode byte ... 错误，使 Docling 的
# 版面模型加载失败（解析被静默降级成占位块）。修复：启用 Python UTF-8 模式并禁用
# torch.compile（变 no-op，绕开 inductor）。必须在解释器启动前设置，否则 exec 重来。
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

from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.common import DocStatus, JobType
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.parsing_docling import docling_available
from app.services.storage import _ALLOWED_EXT
from app.services.task_system import enqueue_job, run_worker_once
from app.services.worker_handlers import HANDLERS
from app.utils.hash import sha256_file
from app.utils.id import doc_id, kb_id

DEFAULT_ROOT = "E:/xaizai/数据库"
# 这些文件夹名不会被当作知识库（用于暂存/临时文件）
SKIP_FOLDERS = {"_导入", "_tmp", "_临时", ".git", ".idea", "__pycache__"}


def _guess_mime(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


async def _get_or_create_kb(session, name: str) -> tuple[KnowledgeBase, bool]:
    """按名称找知识库；找不到则创建。返回 (kb, created)。"""
    kb = (
        await session.execute(select(KnowledgeBase).where(KnowledgeBase.name == name))
    ).scalars().first()
    if kb is not None:
        return kb, False
    kb = KnowledgeBase(
        id=kb_id(),
        name=name,
        description=f"由文件夹「{name}」自动同步创建",
        embedding_model="Qwen3-Embedding-0.6B",
        reranker_model="Qwen3-Reranker-0.6B",
        vision_enabled=False,
        settings={},
    )
    session.add(kb)
    await session.flush()
    return kb, True


async def _existing_hashes(session, kb_id: str) -> set[str]:
    rows = await session.execute(
        select(Document.content_hash).where(Document.kb_id == kb_id)
    )
    return {h for h in rows.scalars().all() if h}


async def _import_one(session, kb: KnowledgeBase, src: Path, existing: set[str]) -> str:
    """导入单个文件到 KB。返回 'imported' / 'skipped'。"""
    content_hash = sha256_file(str(src))
    if content_hash in existing:
        return "skipped"

    did = doc_id()
    ext = src.suffix.lower()
    kb_root = settings.kb_storage_path / kb.id
    kb_root.mkdir(parents=True, exist_ok=True)
    doc_dir = kb_root / did
    doc_dir.mkdir(parents=True, exist_ok=True)
    dest = doc_dir / f"original{ext}"
    shutil.copy2(src, dest)

    doc = Document(
        id=did,
        kb_id=kb.id,
        filename=src.name,
        mime_type=_guess_mime(src),
        ext=ext,
        content_hash=content_hash,
        size_bytes=src.stat().st_size,
        status=DocStatus.PENDING,
        storage_path=str(dest),
    )
    session.add(doc)
    await enqueue_job(
        session, JobType.REINDEX, kb.id,
        doc_id=did,
        payload={"storage_path": str(dest), "ext": ext},
    )
    existing.add(content_hash)
    return "imported"


async def main() -> int:
    ap = argparse.ArgumentParser(
        description="把总数据库根目录下的每个子文件夹同步为一个知识库"
    )
    ap.add_argument("--root", default=DEFAULT_ROOT, help=f"总数据库根目录（默认 {DEFAULT_ROOT}）")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"[ERR] 根目录不存在: {root}")
        return 1

    folders = sorted(
        p for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP_FOLDERS
    )
    print(f"根目录   : {root}")
    print(f"子文件夹 : {len(folders)} 个")
    print(f"Docling  : {'可用' if docling_available() else '不可用（PDF/Office 将退化为占位）'}")

    summary: list[tuple[str, str, bool, int, int, int]] = []
    any_new = False

    async with AsyncSessionLocal() as session:
        for folder in folders:
            files = sorted(
                p for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in _ALLOWED_EXT
            )
            if not files:
                print(f"\n[跳过] {folder.name} —— 空文件夹或无支持的文件")
                continue

            kb, created = await _get_or_create_kb(session, folder.name)
            existing = await _existing_hashes(session, kb.id)
            print(f"\n[知识库] {folder.name}  (id={kb.id}, {'新建' if created else '已存在'})")

            n_imp = n_skip = n_fail = 0
            for f in files:
                try:
                    r = await _import_one(session, kb, f, existing)
                    if r == "imported":
                        n_imp += 1
                        any_new = True
                        print(f"  [导入] {f.name}")
                    else:
                        n_skip += 1
                        print(f"  [跳过] {f.name}（内容已存在）")
                except Exception as e:  # noqa: BLE001
                    n_fail += 1
                    print(f"  [失败] {f.name}: {type(e).__name__}: {e}")
            summary.append((folder.name, kb.id, created, n_imp, n_skip, n_fail))

        await session.commit()

    if any_new:
        print("\nDraining job queue (worker_id=sync-cli) ...")
        cycles = 0
        while await run_worker_once("sync-cli", HANDLERS):
            cycles += 1
        print(f"  worker cycles: {cycles}")

    print("\n== 汇总 ==")
    if not summary:
        print("  没有可处理的文件夹。往子文件夹里放文档后重跑本脚本即可。")
    for name, kid, created, imp, skp, fail in summary:
        flag = "新建" if created else "已有"
        print(f"  「{name}」 {flag}  导入={imp}  跳过={skp}  失败={fail}   (kb={kid})")
    print("\n完成。可在网页 http://127.0.0.1:8000/ 里选择对应知识库开始问答。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
