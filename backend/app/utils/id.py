"""ID generation helpers.

We use prefixed, sortable, collision-resistant IDs (e.g. `kb_01HZ...`) rather than
raw UUIDs for readability in logs/traces.
"""
from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    # 26-char Crockford-ish suffix from UUID; prefix keeps entity types distinct.
    return f"{prefix}_{uuid.uuid4().hex}"


def kb_id() -> str:
    return new_id("kb")


def doc_id() -> str:
    return new_id("doc")


def chunk_id() -> str:
    return new_id("ck")


def job_id() -> str:
    return new_id("job")


def session_id() -> str:
    return new_id("ses")


def eval_id() -> str:
    return new_id("eval")
