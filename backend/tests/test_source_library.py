"""Governed import checks for the configured read-only source library."""
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_session
from app.core.config import settings
from app.main import app
from app.models.document import Document
from app.models.enterprise import AuditEvent, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.services.enterprise import prepare_enterprise_state


FRONTEND_HEADERS = {
    "Origin": "http://localhost:3000",
    "X-Requested-With": "EnterpriseKnowledgeBase",
}


@pytest.fixture
async def enterprise_database():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("""
            CREATE TRIGGER audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'audit events are immutable'); END;
        """))
        await connection.execute(text("""
            CREATE TRIGGER audit_events_no_delete
            BEFORE DELETE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'audit events are immutable'); END;
        """))
    async with session_factory() as session:
        await prepare_enterprise_state(session)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield session_factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_source_branch_import_is_restricted_audited_and_read_only(
    enterprise_database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source_root = tmp_path / "总资料库"
    resume_branch = source_root / "简历"
    product_branch = source_root / "产品文档"
    resume_branch.mkdir(parents=True)
    product_branch.mkdir()
    original = resume_branch / "候选人说明.txt"
    original.write_text("候选人资料，仅用于受限导入。", encoding="utf-8")
    (resume_branch / "不支持.exe").write_bytes(b"not-importable")
    storage_root = tmp_path / "managed-storage"

    monkeypatch.setattr(settings, "knowledge_source_root", str(source_root))
    monkeypatch.setattr(settings, "kb_storage_dir", str(storage_root))
    monkeypatch.setattr(settings, "knowledge_source_scan_limit", 100)
    monkeypatch.setattr(settings, "knowledge_source_import_limit", 20)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as admin:
        bootstrap = await admin.post(
            "/api/v1/auth/bootstrap",
            headers=FRONTEND_HEADERS,
            json={
                "organization_name": "示例企业",
                "display_name": "系统管理员",
                "email": "admin@example.com",
                "password": "Admin-Password-2026",
            },
        )
        assert bootstrap.status_code == 201, bootstrap.text
        department = await admin.post(
            "/api/v1/departments",
            headers=FRONTEND_HEADERS,
            json={"name": "人力资源部", "code": "hr", "description": "人员资料"},
        )
        assert department.status_code == 201, department.text
        department_id = department.json()["id"]

        branches = await admin.get("/api/v1/source-library/branches")
        assert branches.status_code == 200, branches.text
        body = branches.json()
        assert body["available"] is True
        assert body["read_only"] is True
        resume = next(item for item in body["branches"] if item["name"] == "简历")
        assert resume["total_file_count"] == 2
        assert resume["importable_file_count"] == 1
        assert resume["unsupported_file_count"] == 1
        assert resume["sensitive"] is True
        assert resume["recommended_access_scope"] == "restricted"
        assert "候选人说明" not in branches.text

        traversal = await admin.post(
            "/api/v1/source-library/imports",
            headers=FRONTEND_HEADERS,
            json={
                "branch_name": "../简历",
                "department_id": department_id,
                "access_scope": "restricted",
            },
        )
        assert traversal.status_code == 400

        unsafe_share = await admin.post(
            "/api/v1/source-library/imports",
            headers=FRONTEND_HEADERS,
            json={
                "branch_name": "简历",
                "department_id": department_id,
                "access_scope": "department",
            },
        )
        assert unsafe_share.status_code == 400

        imported = await admin.post(
            "/api/v1/source-library/imports",
            headers=FRONTEND_HEADERS,
            json={
                "branch_name": "简历",
                "department_id": department_id,
                "access_scope": "restricted",
            },
        )
        assert imported.status_code == 200, imported.text
        result = imported.json()
        assert result["created_knowledge_base"] is True
        assert result["imported_count"] == 1
        assert result["skipped_duplicate_count"] == 0
        assert result["unsupported_count"] == 1
        assert len(result["job_ids"]) == 1

        repeated = await admin.post(
            "/api/v1/source-library/imports",
            headers=FRONTEND_HEADERS,
            json={
                "branch_name": "简历",
                "department_id": department_id,
                "access_scope": "restricted",
            },
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["imported_count"] == 0
        assert repeated.json()["skipped_duplicate_count"] == 1

    assert original.read_text(encoding="utf-8") == "候选人资料，仅用于受限导入。"
    assert (resume_branch / "不支持.exe").is_file()

    async with enterprise_database() as session:
        kb = (await session.execute(select(KnowledgeBase).where(KnowledgeBase.name == "简历"))).scalar_one()
        scope = (
            await session.execute(
                select(KnowledgeBaseScope).where(KnowledgeBaseScope.kb_id == kb.id)
            )
        ).scalar_one()
        document = (
            await session.execute(select(Document).where(Document.kb_id == kb.id))
        ).scalar_one()
        actions = set((await session.execute(select(AuditEvent.action))).scalars().all())
        assert scope.department_id == department_id
        assert scope.access_scope == "restricted"
        assert Path(document.storage_path).resolve().is_relative_to(storage_root.resolve())
        assert Path(document.storage_path).read_text(encoding="utf-8") == original.read_text(encoding="utf-8")
        assert "document.source_imported" in actions
        assert "source_branch.imported" in actions
