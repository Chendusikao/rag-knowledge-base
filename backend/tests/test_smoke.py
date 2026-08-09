"""Import-level smoke test (run after `pip install -r requirements.txt`).

The full pipeline smoke (KB -> index -> retrieve) lives in scripts/smoke.py.
This test only verifies that the app module graph imports cleanly.
"""
import importlib

import httpx
import pytest


def test_import_app():
    importlib.import_module("app.main")
    importlib.import_module("app.api.routers.chat")
    importlib.import_module("app.services.retrieval.manager")
    importlib.import_module("app.services.task_system")


@pytest.mark.asyncio
async def test_backend_root_redirects_to_docs():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        response = await client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
