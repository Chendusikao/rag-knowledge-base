"""Secret resolution (PLAN 3: API keys live in Windows Credential Manager).

This is a STUB. The SQLite ``provider_profiles`` table stores only a
``credential_ref`` (a reference), never the secret. The real implementation
should call the Windows Credential Manager (e.g. via ``keyring`` with the
Win32Cred backend, or ``powershell Get-Secret``). Until then we resolve from an
optional environment variable mapped by ref, and otherwise return None.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("rag.providers.secrets")


def get_secret(credential_ref: str | None) -> str | None:
    """Resolve a credential reference to its secret value.

    TODO: integrate Windows Credential Manager. For now:
      * if ``credential_ref`` looks like ``env:NAME``, read ``NAME`` from env;
      * else try ``RAG_SECRET_<ref>`` environment variable;
      * else return None (caller should surface a clear "secret not configured").
    """
    if not credential_ref:
        return None
    if credential_ref.startswith("env:"):
        name = credential_ref[len("env:"):]
        return os.environ.get(name)
    return os.environ.get(f"RAG_SECRET_{credential_ref}")
