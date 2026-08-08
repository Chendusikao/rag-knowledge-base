#!/usr/bin/env python3
"""
检查重索引后各知识库实际使用的 parser_version 分布。
用法：
    E:/xaizai/wendaxitog/backend/.venv/Scripts/python.exe backend/scripts/check_parser_versions.py
"""
from __future__ import annotations

import pathlib
import sqlite3
import sys


def main() -> int:
    # 项目根目录 = 脚本目录的父目录
    script_dir = pathlib.Path(__file__).resolve().parent
    backend_dir = script_dir.parent
    db_path = backend_dir / "app" / "data" / "rag.db"

    if not db_path.exists():
        print(f"[ERR] 数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    tables = ["document_versions", "chunks"]
    for table in tables:
        print(f"\n== {table}.parser_version ==")
        try:
            rows = cur.execute(
                f"SELECT parser_version, COUNT(*) AS cnt FROM {table} GROUP BY parser_version ORDER BY cnt DESC"
            ).fetchall()
        except sqlite3.OperationalError as e:
            print(f"  查询失败: {e}")
            continue

        if not rows:
            print("  (无数据)")
            continue

        total = sum(r["cnt"] for r in rows)
        for r in rows:
            version = r["parser_version"] or "(NULL)"
            cnt = r["cnt"]
            pct = cnt / total * 100 if total else 0
            print(f"  {version:20s} {cnt:6d} ({pct:5.1f}%)")
        print(f"  {'TOTAL':20s} {total:6d}")

    # 顺手列出最近 5 条 document_versions 的元数据
    print("\n== 最近 5 条 document_versions ==")
    rows = cur.execute(
        "SELECT id, doc_id, parser_version, version, created_at "
        "FROM document_versions ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(
            f"  id={r['id'][:12]:12s} doc_id={r['doc_id'][:12]:12s} "
            f"version={r['version']:3d} parser={r['parser_version'] or '(NULL)':14s} "
            f"created_at={r['created_at']}"
        )

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
