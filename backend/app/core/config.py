"""Application configuration.

All runtime settings live here. Secrets (cloud API keys) are NOT stored in config
or SQLite — only a reference + capability info per PLAN.md (Windows Credential Manager).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = backend/ directory
BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        extra="ignore",
        env_file=BACKEND_ROOT.parent / ".env",
        env_file_encoding="utf-8",
    )

    # ---- Paths ----
    data_dir: str = str(DATA_DIR)
    # SQLite WAL single file for business state, jobs, chat, cache, evaluation.
    # Use the aiosqlite async driver (PLAN: SQLite WAL).
    sqlite_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'rag.db'}"

    # Knowledge-base专属原文件目录
    kb_storage_dir: str = str(DATA_DIR / "kb_files")

    # ---- Server ----
    host: str = "127.0.0.1"
    port: int = 8000
    cors_allow_origins: list[str] = ["http://localhost:3000"]

    # ---- Indexing limits (PLAN 3.Offline) ----
    max_file_bytes: int = 100 * 1024 * 1024  # 100 MB
    max_pdf_pages: int = 500

    # ---- Retrieval defaults (PLAN 3.Online) ----
    default_retrieval_mode: str = "balanced"  # fast | balanced | deep
    context_token_budget: int = 8000

    # ---- Provider ----
    # Default provider so the system runs with NO GPU / cloud key.
    default_llm_provider: str = "mock"
    default_embedding_provider: str = "mock"
    default_vision_provider: str = "mock"
    default_agent_provider: str = "mock"

    # Local embedding model path/id (PLAN: real local embeddings). Only used when
    # default_embedding_provider == "local". Default BGE-M3 (1024-dim, 100+ langs,
    # multilingual; weights ~2.3GB, downloaded once from HF on first load).
    local_embedding_model: str = "BAAI/bge-m3"

    # Local directory containing embedding model files. When set, the ``local``
    # embedding provider loads from this folder directly (no internet download) —
    # use this when model-weight CDNs are unreachable. Takes priority over
    # ``local_embedding_model``. Leave empty to auto-download by model id.
    local_embedding_model_path: str = ""

    # Dimension for the zero-download local-lexical embedding (local-lexical kind).
    # Must match the dense store / Chroma collection dimension. Keep 1024 to stay
    # compatible with the BGE-M3 path (so switching providers never reshapes data).
    local_embedding_dim: int = 1024

    # ---- DeepSeek (PLAN: real model integration) ----
    # OpenAI-compatible chat/embeddings endpoint. Secret comes from env/.env only.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Reranker selection: "none" keeps RRF order; "deepseek" uses DeepSeek as an
    # LLM-as-reranker over the RRF-fused candidates. Requires deepseek_api_key.
    rerank_provider: str = "none"

    # ---- Document parsing ----
    # Parser for PDF / Office / image docs: "docling" (real layout-aware
    # extraction), "legacy" (single placeholder chunk), or "auto" (docling if
    # installed, else legacy). Markdown/plain-text always use the structured
    # markdown chunker regardless of this setting.
    doc_parser: str = "docling"

    # Enable OCR for images / scanned PDFs. Requires the easyocr model; off by
    # default so Docling does not pull large OCR models during first run.
    docling_ocr: bool = False

    # ---- Task system ----
    worker_lease_seconds: int = 30          # 租约时长
    worker_heartbeat_seconds: int = 10      # 心跳间隔
    max_job_retries: int = 3
    job_stale_after_seconds: int = 300      # 超过此时长未心跳视为需恢复

    @property
    def kb_storage_path(self) -> Path:
        p = Path(self.kb_storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
