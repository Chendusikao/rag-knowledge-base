#!/usr/bin/env python3
"""
批量同步：把「总数据库根目录」下的每个子文件夹，同步为一个知识库。

用法（在 backend 目录下）：
  .venv/Scripts/python.exe scripts/sync_folders_to_kbs.py \
      [--root E:/path/to/enterprise-library]

规则：
  1. root 的每个「直接子文件夹」= 一个知识库，KB 名 = 文件夹名。
     （例：<总资料库>/简历/ -> 知识库「简历」）
  2. 只处理系统支持的扩展名（PDF/Word/PPT/Excel/图片/HTML/md/txt），其余自动忽略。
  3. 增量同步：按「内容哈希」去重——同一 KB 里已存在相同内容的文档自动跳过；
     文件改过内容会重新导入；文件改名不影响去重。
  4. 空文件夹跳过（不建库），放文件后再跑一次即自动建库导入。
  5. 不依赖后端在线：直接驱动 service 层 + 内置 worker 完成解析入库。

安全：脚本只做「复制入库」，不会删除你文件夹里的任何文件；默认使用受限访问。
      企业环境优先使用网页“总资料库”入口，以记录真实操作人。
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

# Make the backend package importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.models.common import DocStatus, JobType, KnowledgeAccessScope
from app.models.document import Document
from app.models.enterprise import DEFAULT_DEPARTMENT_ID, Department
from app.models.knowledge_base import KnowledgeBase
from app.services.parsing_docling import docling_available
from app.services.audit import record_audit
from app.services.enterprise import get_or_create_scope, prepare_enterprise_state
from app.services.storage import _ALLOWED_EXT, copy_source_file
from app.services.task_system import enqueue_job, run_worker_once
from app.services.worker_handlers import HANDLERS
from app.utils.hash import sha256_file
from app.utils.id import kb_id

DEFAULT_ROOT = settings.knowledge_source_root
# 这些文件夹名不会被当作知识库（用于暂存/临时文件）
SKIP_FOLDERS = {"_导入", "_tmp", "_临时", ".git", ".idea", "__pycache__"}


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


async def _import_one(
    session,
    kb: KnowledgeBase,
    src: Path,
    existing: set[str],
    department_id: str,
) -> str:
    """导入单个文件到 KB。返回 'imported' / 'skipped'。"""
    content_hash = sha256_file(str(src))
    if content_hash in existing:
        return "skipped"

    meta = copy_source_file(kb.id, src, src.name)

    doc = Document(
        id=meta["doc_id"],
        kb_id=kb.id,
        filename=meta["filename"],
        mime_type=meta["mime_type"],
        ext=meta["ext"],
        content_hash=content_hash,
        size_bytes=meta["size_bytes"],
        status=DocStatus.PENDING,
        storage_path=meta["storage_path"],
    )
    session.add(doc)
    await enqueue_job(
        session, JobType.REINDEX, kb.id,
        doc_id=doc.id,
        payload={"storage_path": meta["storage_path"], "ext": meta["ext"]},
        commit=False,
    )
    await record_audit(
        session,
        action="document.source_imported",
        resource_type="document",
        resource_id=doc.id,
        department_id=department_id,
        details={"source_branch": src.parent.name, "extension": doc.ext, "size_bytes": doc.size_bytes},
    )
    existing.add(content_hash)
    return "imported"


async def main() -> int:
    ap = argparse.ArgumentParser(
        description="把总数据库根目录下的每个子文件夹同步为一个知识库"
    )
    ap.add_argument("--root", default=DEFAULT_ROOT, help=f"总数据库根目录（默认 {DEFAULT_ROOT}）")
    ap.add_argument(
        "--department-id",
        default=DEFAULT_DEPARTMENT_ID,
        help="导入后所属部门 ID（默认企业公共部门）",
    )
    ap.add_argument(
        "--access-scope",
        choices=[KnowledgeAccessScope.RESTRICTED, KnowledgeAccessScope.DEPARTMENT],
        default=KnowledgeAccessScope.RESTRICTED,
        help="默认受限；选择 department 还需要 --confirm-department-access",
    )
    ap.add_argument(
        "--confirm-department-access",
        action="store_true",
        help="明确确认所选部门全部成员默认可查看",
    )
    args = ap.parse_args()

    if args.access_scope == KnowledgeAccessScope.DEPARTMENT and not args.confirm_department_access:
        print("[ERR] 部门共享需要同时传入 --confirm-department-access")
        return 2

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

    await init_db()
    async with AsyncSessionLocal() as session:
        await prepare_enterprise_state(session)
        department = await session.get(Department, args.department_id)
        if department is None or not department.is_active:
            print(f"[ERR] 部门不存在或已停用: {args.department_id}")
            return 2
        for folder in folders:
            files = sorted(
                p for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in _ALLOWED_EXT
            )
            if not files:
                print(f"\n[跳过] {folder.name} —— 空文件夹或无支持的文件")
                continue

            kb, created = await _get_or_create_kb(session, folder.name)
            scope = await get_or_create_scope(
                session,
                kb.id,
                department_id=department.id,
                access_scope=args.access_scope,
            )
            scope.department_id = department.id
            scope.access_scope = args.access_scope
            kb.settings = {
                **(kb.settings or {}),
                "source_library_branch": folder.name,
                "source_copy_mode": "managed_copy",
            }
            existing = await _existing_hashes(session, kb.id)
            print(f"\n[知识库] {folder.name}  (id={kb.id}, {'新建' if created else '已存在'})")

            n_imp = n_skip = n_fail = 0
            for f in files:
                try:
                    r = await _import_one(session, kb, f, existing, department.id)
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
            await record_audit(
                session,
                action="source_branch.imported",
                resource_type="knowledge_base",
                resource_id=kb.id,
                department_id=department.id,
                details={
                    "source_branch": folder.name,
                    "access_scope": args.access_scope,
                    "created_knowledge_base": created,
                    "imported_count": n_imp,
                    "skipped_duplicate_count": n_skip,
                    "failed_count": n_fail,
                    "actor_source": "local_cli",
                },
            )

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
    print("\n完成。可在网页 http://localhost:3000/chat 里选择对应知识库开始问答。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
