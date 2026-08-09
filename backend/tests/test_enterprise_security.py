"""End-to-end enterprise auth, department, ACL and audit checks."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.enterprise import AuditEvent
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
async def test_department_acl_and_immutable_audit(enterprise_database):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as admin:
        status = await admin.get("/api/v1/auth/status")
        assert status.status_code == 200
        assert status.json()["setup_required"] is True

        missing_csrf = await admin.post(
            "/api/v1/auth/bootstrap",
            headers={"Origin": "http://localhost:3000"},
            json={
                "organization_name": "示例企业",
                "display_name": "系统管理员",
                "email": "admin@example.com",
                "password": "Admin-Password-2026",
            },
        )
        assert missing_csrf.status_code == 403

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
        assert bootstrap.json()["system_role"] == "admin"

        department_response = await admin.post(
            "/api/v1/departments",
            headers=FRONTEND_HEADERS,
            json={"name": "销售部", "code": "sales", "description": "销售资料"},
        )
        assert department_response.status_code == 201, department_response.text
        department = department_response.json()

        kb_response = await admin.post(
            "/api/v1/knowledge-bases",
            headers=FRONTEND_HEADERS,
            json={
                "name": "销售知识库",
                "description": "销售制度与产品资料",
                "department_id": department["id"],
                "access_scope": "restricted",
            },
        )
        assert kb_response.status_code == 200, kb_response.text
        kb = kb_response.json()
        assert kb["department_name"] == "销售部"
        assert kb["access_level"] == "manager"

        user_response = await admin.post(
            "/api/v1/users",
            headers=FRONTEND_HEADERS,
            json={
                "email": "member@example.com",
                "display_name": "销售成员",
                "department_id": department["id"],
                "system_role": "member",
                "temporary_password": "Member-Password-2026",
            },
        )
        assert user_response.status_code == 201, user_response.text
        member = user_response.json()
        assert member["must_change_password"] is True

        permission_response = await admin.put(
            f"/api/v1/knowledge-bases/{kb['id']}/permissions",
            headers=FRONTEND_HEADERS,
            json={"user_id": member["id"], "access_level": "viewer"},
        )
        assert permission_response.status_code == 200, permission_response.text

        security_response = await admin.get("/api/v1/security/status")
        assert security_response.status_code == 200
        assert "PBKDF2" in security_response.json()["password_storage"]

    async with AsyncClient(transport=transport, base_url="http://testserver") as member_client:
        login = await member_client.post(
            "/api/v1/auth/login",
            headers=FRONTEND_HEADERS,
            json={"email": "member@example.com", "password": "Member-Password-2026"},
        )
        assert login.status_code == 200, login.text

        kbs = await member_client.get("/api/v1/knowledge-bases")
        assert kbs.status_code == 200
        assert [item["id"] for item in kbs.json()] == [kb["id"]]
        assert kbs.json()[0]["access_level"] == "viewer"

        denied = await member_client.delete(
            f"/api/v1/knowledge-bases/{kb['id']}", headers=FRONTEND_HEADERS
        )
        assert denied.status_code == 403

        security_denied = await member_client.get("/api/v1/security/status")
        assert security_denied.status_code == 403

    async with enterprise_database() as session:
        events = (await session.execute(select(AuditEvent))).scalars().all()
        actions = {event.action for event in events}
        assert {
            "auth.bootstrap",
            "department.created",
            "knowledge_base.created",
            "user.created",
            "permission.granted",
            "permission.denied",
        }.issubset(actions)

        with pytest.raises(IntegrityError):
            await session.execute(
                update(AuditEvent)
                .where(AuditEvent.id == events[0].id)
                .values(outcome="tampered")
            )
            await session.commit()
        await session.rollback()
