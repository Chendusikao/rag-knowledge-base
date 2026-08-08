"""Docling-based real document parsing.

Replaces the scaffold placeholder parser for PDF / Office / image formats with
true layout-aware extraction. A ``DoclingDocument`` is turned into ``ChunkSpec``
objects that carry the *real* ``page_number``, section hierarchy
(``section_path``) and ``modality`` (text / table / image), instead of a single
"parsing pending" placeholder.

``docling`` is imported lazily inside :func:`convert_document` so this module
imports cleanly even when the optional heavy dependency is absent — the rest of
the application stays importable and the caller (``parsing.parse_document``)
falls back to the legacy parser when Docling is missing or fails.
"""
from __future__ import annotations

import os

# 纵深防御：torch.compile 会在中文 Windows 上触发 inductor 用 GBK 解码 UTF-8 的
# CUDA kernel 模板文件而崩溃，使 Docling 版面模型加载失败。TORCH_COMPILE_DISABLE
# 是 torch 在每次 compile() 调用时运行时检查的环境变量，因此在这里（docling
# import 之前）设置即可让 Docling 安全加载，即便 backend 进程启动时忘了设该变量。
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

from app.services.parsing_types import ChunkSpec, _split_overlap

DOC_PARSER_VERSION = "docling-1.0"

# File types Docling can attempt to parse. (.txt/.md are handled by parse_markdown.)
DOCLING_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff",
}

# Whole-image files: their OCR text is the entire content (no sections/tables).
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

# Label values (from DocItemLabel) we treat as dedicated non-text blocks.
_TABLE_LABELS = {"table"}
_PICTURE_LABELS = {"picture", "image"}
_HEADING_LABELS = {"section_header", "title"}


def docling_available() -> bool:
    """Return True if the ``docling`` package can be imported."""
    try:
        import docling  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _label_value(item) -> str:
    label = getattr(item, "label", None)
    if label is None:
        return ""
    return label.value if hasattr(label, "value") else str(label)


def _page_of(item) -> int:
    try:
        prov = getattr(item, "prov", None)
        if prov:
            return int(prov[0].page_no) or 0
    except Exception:  # noqa: BLE001
        pass
    return 0


def _text_of(item) -> str:
    try:
        t = getattr(item, "text", None)
        if isinstance(t, str):
            return t.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


# RapidOCR 引擎（懒加载、全局复用）。Docling 的 do_ocr 只对「整页扫描」识别，
# 文档内嵌图片（docx/pdf 里的配图/证书照片）不会自动出文字，这里手动补一轮 OCR。
_ocr_engine = None


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def _picture_text(item) -> str:
    """对单个文档内嵌图片运行 RapidOCR，返回识别出的文字（失败返回空串）。"""
    try:
        img_ref = getattr(item, "image", None)
        pil = None
        if img_ref is not None:
            pil = getattr(img_ref, "pil_image", None)
            if pil is None:
                pil = getattr(img_ref, "image", None)
        if pil is None:
            return ""
        engine = _get_ocr_engine()
        result, _ = engine(pil)
        if not result:
            return ""
        lines = [str(line[1]).strip() for line in result
                 if len(line) >= 2 and line[1]]
        return "\n".join(lines).strip()
    except Exception:  # noqa: BLE001
        return ""


def _table_markdown(item) -> str:
    for fn in ("export_to_markdown", "to_markdown"):
        fn_obj = getattr(item, fn, None)
        if callable(fn_obj):
            try:
                out = fn_obj()
                if out:
                    return out.strip()
            except Exception:  # noqa: BLE001
                continue
    return _text_of(item)


def convert_document(path: str, ext: str, enable_ocr: bool = False) -> list[ChunkSpec]:
    """Parse ``path`` with Docling into structured ``ChunkSpec`` objects.

    Raises on any failure so the caller can fall back to the legacy parser.
    When ``enable_ocr`` is True, PDFs and images are OCR'd with RapidOCR
    (Chinese + English, onnxruntime backend; models ship with the docling
    package, so no extra install is needed). Scanned / photographed documents
    then produce real text instead of the "no OCR" placeholder.
    """
    from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions

    if enable_ocr:
        # PDF 与图片（ImageFormatOption 内部复用 StandardPdfPipeline）统一开启 OCR。
        pdf_opts = PdfPipelineOptions()
        pdf_opts.do_ocr = True
        pdf_opts.ocr_options = RapidOcrOptions()  # 默认中文，onnxruntime，模型随包自带
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=pdf_opts),
            }
        )
    else:
        converter = DocumentConverter()
    result = converter.convert(path)
    doc = result.document

    # 整图文件：OCR 文本即全部内容（docling 会把整图识别为标题样 item，
    # 走通用遍历会吞掉文本），这里直接整体产出，不做章节/表格切分。
    if ext in _IMAGE_EXTENSIONS:
        parts = [_text_of(item) for item, _ in doc.iterate_items()]
        full = "\n".join(p for p in parts if p).strip()
        if not full:
            full = ("（图片已通过 Docling 解析：未识别出文字内容。"
                    "请确认图片包含清晰文字，或检查 RAG_DOCLING_OCR 配置。）")
        return [
            ChunkSpec(content=piece, section_path=[], page_number=1, modality="image")
            for piece in _split_overlap(full)
        ]

    chunks: list[ChunkSpec] = []
    section_stack: list[tuple[int, str]] = []
    cur_path: list[str] = []
    buf: list[str] = []
    buf_page: int = 0
    cur_page = 0

    def flush() -> None:
        joined = "\n".join(buf).strip()
        if not joined:
            return
        for piece in _split_overlap(joined):
            chunks.append(ChunkSpec(content=piece, section_path=list(cur_path),
                                    page_number=buf_page, modality="text"))

    for item, level in doc.iterate_items():
        label = _label_value(item)
        page = _page_of(item)
        if page:
            cur_page = page

        if label in _TABLE_LABELS:
            flush()
            buf = []
            buf_page = 0
            md = _table_markdown(item)
            if md:
                chunks.append(ChunkSpec(content=md, section_path=list(cur_path),
                                        page_number=cur_page, modality="table"))
            continue

        if label in _PICTURE_LABELS:
            flush()
            buf = []
            buf_page = 0
            ocr = _text_of(item)
            if not ocr and enable_ocr:
                ocr = _picture_text(item)
            if ocr:
                for piece in _split_overlap(ocr):
                    chunks.append(ChunkSpec(content=piece, section_path=list(cur_path),
                                            page_number=cur_page, modality="image"))
            else:
                chunks.append(ChunkSpec(
                    content="（文档内嵌图片：未识别出文字内容。若是截图/证书等含文字的图片，"
                            "请确认 backend/.env 已设置 RAG_DOCLING_OCR=true 后重新索引。）",
                    section_path=list(cur_path), page_number=cur_page, modality="image"))
            continue

        text = _text_of(item)
        if not text:
            continue

        if label in _HEADING_LABELS:
            flush()
            buf = []
            buf_page = 0
            section_stack = [(lv, t) for (lv, t) in section_stack if lv < level]
            section_stack.append((level, text))
            cur_path = [t for _, t in section_stack]
        else:
            if not buf:
                buf_page = page
            buf.append(text)

    flush()
    if not chunks:
        # 兜底：整页内容被版面模型标为标题（常见于整页扫描件/OCR 页）时，上面的
        # 遍历只会把它记作章节而吞掉正文；这里把所有文本项作为内容整体产出，
        # 保证 OCR 出来的文字一定能被检索到。
        parts = [_text_of(item) for item, _ in doc.iterate_items()]
        full = "\n".join(p for p in parts if p).strip()
        if full:
            chunks = [
                ChunkSpec(content=piece, section_path=[], page_number=1, modality="text")
                for piece in _split_overlap(full)
            ]
    return chunks
