"""Docling parsing integration check.

Usage:
  python scripts/test_docling_parsing.py                 # assembly + markdown + fallback + mock checks
  python scripts/test_docling_parsing.py --file X.pdf    # also real Docling parse (downloads models on first run)

In the sandbox the lightweight checks run without triggering any model
download. Pass --file on a machine with network access to exercise the real
Docling extraction (layout/table models are fetched from HuggingFace once).
"""
import argparse
import sys
import tempfile
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services import parsing  # noqa: E402
from app.services.parsing_docling import docling_available  # noqa: E402


def check_assembly() -> bool:
    ok = docling_available()
    print(f"[1] docling importable: {ok}")
    if ok:
        try:
            import docling

            print(f"    docling version: {getattr(docling, '__version__', '?')}")
        except Exception:  # noqa: BLE001
            pass
    return ok


def check_markdown() -> None:
    md = "# Title\n\nSome paragraph text here.\n\n## Section\n\nMore text."
    tmp = Path(tempfile.gettempdir()) / "test_docling_md.md"
    tmp.write_text(md, encoding="utf-8")
    specs = parsing.parse_document(str(tmp), ".md")
    assert specs, "markdown should yield chunks"
    print(f"[2] markdown parse OK: {len(specs)} chunks, first page={specs[0].page_number}")
    assert parsing.parser_version_for(".md") == "md-0.1"
    print("    parser_version_for(.md) = md-0.1 OK")
    tmp.unlink(missing_ok=True)


def check_fallback() -> None:
    if not docling_available():
        print("[3] docling not installed -> .pdf uses legacy placeholder (expected).")
        specs = parsing.parse_document("nonexistent.pdf", ".pdf")
        assert specs and "占位" in specs[0].content, "expected placeholder"
        print(f"    fallback placeholder present: {specs[0].content[:30]!r}")
        return
    # Simulate convert() failing (e.g. model download blocked) -> graceful fallback.
    from unittest.mock import patch

    def boom(*a, **k):
        raise RuntimeError("simulated model download failure")

    with patch("app.services.parsing.convert_document", boom):
        specs = parsing.parse_document("nonexistent.pdf", ".pdf")
    assert specs and "占位" in specs[0].content, "expected placeholder after failure"
    print("[3] docling present but convert fails -> graceful placeholder fallback OK")
    print(f"    fallback placeholder: {specs[0].content[:30]!r}")


def check_convert_mock() -> None:
    """Verify convert_document's traversal logic without downloading models."""
    from unittest.mock import MagicMock, patch

    import app.services.parsing_docling as pd

    def mk(label_value, text, page_no, **kw):
        it = MagicMock()
        it.label.value = label_value
        it.text = text
        it.prov = [MagicMock(page_no=page_no)]
        for k, v in kw.items():
            setattr(it, k, v)
        return it

    head = mk("section_header", "My Section", 3)
    body = mk("text", "Hello world paragraph.", 3)
    table = mk("table", "", 4)
    table.export_to_markdown.return_value = "| a | b |\n|---|---|\n| 1 | 2 |"
    pic = mk("picture", "", 5)  # no OCR text -> placeholder

    fake_doc = MagicMock()
    fake_doc.iterate_items.return_value = [(head, 1), (body, 2), (table, 2), (pic, 2)]
    fake_result = MagicMock()
    fake_result.document = fake_doc
    fake_converter = MagicMock()
    fake_converter.convert.return_value = fake_result

    with patch("docling.document_converter.DocumentConverter", return_value=fake_converter):
        chunks = pd.convert_document("fake.pdf", ".pdf")

    mods = Counter(c.modality for c in chunks)
    pages = sorted({c.page_number for c in chunks})
    print(f"[4] convert_document mock OK: {len(chunks)} chunks, modality={dict(mods)}, pages={pages}")
    assert any(c.modality == "table" for c in chunks), "expected a table chunk"
    assert any(c.modality == "image" for c in chunks), "expected an image chunk"
    assert any("My Section" in c.section_path for c in chunks), "expected section path"
    assert pages == [3, 4, 5], f"unexpected pages {pages}"
    print("    section/page/modality extraction verified")


def check_real_file(path: str) -> None:
    print(f"[5] real Docling parse of {path} ...")
    specs = parsing.parse_document(path, Path(path).suffix)
    mods = Counter(s.modality for s in specs)
    pages = Counter(s.page_number for s in specs)
    print(f"    chunks={len(specs)} modality={dict(mods)} pages={dict(pages)}")
    for s in specs[:5]:
        print(f"    - p{s.page_number} [{s.modality}] {s.content[:50]!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="path to a real doc to parse with Docling")
    args = ap.parse_args()
    ok = check_assembly()
    check_markdown()
    check_fallback()
    check_convert_mock()
    if args.file:
        check_real_file(args.file)
    print(f"\nDOCLING_CHECK_DONE (docling_available={ok})")


if __name__ == "__main__":
    main()
