"""Import-level smoke test (run after `pip install -r requirements.txt`).

The full pipeline smoke (KB -> index -> retrieve) lives in scripts/smoke.py.
This test only verifies that the app module graph imports cleanly.
"""
import importlib


def test_import_app():
    importlib.import_module("app.main")
    importlib.import_module("app.api.routers.chat")
    importlib.import_module("app.services.retrieval.manager")
    importlib.import_module("app.services.task_system")
