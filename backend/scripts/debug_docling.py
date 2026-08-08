#!/usr/bin/env python3
"""Minimal Docling debug: call convert_document() once and dump the full traceback.

This bypasses the parse_document() try/except wrapper so the real reason a PDF
fails to parse is always visible.
"""
from __future__ import annotations

import argparse
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description="Print the exact Docling error for one file")
    ap.add_argument(
        "file_pos",
        nargs="?",
        default=None,
        metavar="FILE",
        help="local PDF/Word/PPT/Excel/image/HTML (positional)",
    )
    ap.add_argument("--file", dest="file_flag", default=None,
                    metavar="FILE", help="alias for positional file")
    args = ap.parse_args()
    file_path = args.file_flag or args.file_pos
    if not file_path:
        ap.error("path required: pass as positional FILE or via --file FILE")

    src = Path(file_path).expanduser().resolve()
    if not src.is_file():
        print(f"[ERR] file not found: {src}")
        return 1
    ext = src.suffix.lower()
    print(f"file      : {src}")
    print(f"size      : {src.stat().st_size} bytes")
    print(f"ext       : {ext}")
    print()

    # Lazy imports so we still see python import errors clearly.
    from app.services.parsing_docling import convert_document, docling_available, DOCLING_EXTENSIONS, DOC_PARSER_VERSION
    print(f"docling_available: {docling_available()}")
    print(f"docling_version  : {DOC_PARSER_VERSION}")
    print(f"DOCLING_EXTENSIONS: {sorted(DOCLING_EXTENSIONS)}")
    if ext not in DOCLING_EXTENSIONS:
        print(f"[WARN] {ext} is NOT in DOCLING_EXTENSIONS; convert_document will refuse")
    print()

    print("[call] convert_document(path, ext, enable_ocr=False) ...")
    try:
        specs = convert_document(str(src), ext, enable_ocr=False)
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"\n[FAILED] {type(e).__name__}: {e}")
        print("\n--- full traceback ---")
        traceback.print_exc()
        print("--- end traceback ---")
        return 2

    print(f"[OK] {len(specs)} chunks produced")
    for i, s in enumerate(specs[:10]):
        preview = (s.content or "").replace("\n", " ")[:90]
        print(f"  #{i} page={s.page_number} modality={s.modality} sec={s.section_path}")
        print(f"        {preview}")
    if len(specs) > 10:
        print(f"  ... ({len(specs) - 10} more)")
    return 0


if __name__ == "__main__":
    sys.exit(main())