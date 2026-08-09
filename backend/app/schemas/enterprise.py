"""Schemas for enterprise authentication, departments, permissions and audit."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


SYSTEM_ROLES = {"admin", "department_manager", "member", "auditor"}
ACCESS_LEVELS = {"viewer", "editor", "manager"}
ACCESS_SCOPES = {"department", "restricted"}


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = Field(default="", max_length=2000)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    code: str
    description: str
    is_active: bool
    user_count: int = 0
    knowledge_base_count: int = 0
    created_at: datetime
    updated_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    department_id: str | None
    department_name: str | None = None
    system_role: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class AuthStatusOut(BaseModel):
    setup_required: bool
    authenticated: bool
    user: UserOut | None = None


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=255)
    department_id: str | None = None
    system_role: str = "member"
    temporary_password: str = Field(min_length=12, max_length=256)

    @field_validator("system_role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        if value not in SYSTEM_ROLES:
            raise ValueError("invalid system role")
        return value


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    department_id: str | None = None
    system_role: str | None = None
    is_active: bool | None = None

    @field_validator("system_role")
    @classmethod
    def valid_role(cls, value: str | None) -> str | None:
        if value is not None and value not in SYSTEM_ROLES:
            raise ValueError("invalid system role")
        return value


class PasswordResetRequest(BaseModel):
    temporary_password: str = Field(min_length=12, max_length=256)


class PermissionSet(BaseModel):
    user_id: str
    access_level: str

    @field_validator("access_level")
    @classmethod
    def valid_level(cls, value: str) -> str:
        if value not in ACCESS_LEVELS:
            raise ValueError("invalid access level")
        return value


class PermissionOut(BaseModel):
    id: str
    kb_id: str
    user_id: str
    user_email: str
    user_display_name: str
    access_level: str
    granted_by: str | None
    created_at: datetime
    updated_at: datetime


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_user_id: str | None
    actor_email: str
    action: str
    resource_type: str
    resource_id: str
    department_id: str | None
    outcome: str
    request_id: str
    ip_address: str
    user_agent: str
    details: dict
    created_at: datetime


class AuditEventList(BaseModel):
    items: list[AuditEventOut]
    total: int
    limit: int
    offset: int


class SecurityStatusOut(BaseModel):
    authentication: str
    password_storage: str
    session_cookie: str
    csrf_protection: str
    audit_log: str
    storage_encryption: str
    storage_encryption_configured: bool


class SourceBranchOut(BaseModel):
    name: str
    total_file_count: int
    supported_file_count: int
    importable_file_count: int
    unsupported_file_count: int
    oversized_file_count: int
    total_size_bytes: int
    extension_counts: dict[str, int]
    last_modified_at: datetime | None
    sensitive: bool
    recommended_access_scope: str
    truncated: bool


class SourceLibraryOut(BaseModel):
    root: str
    available: bool
    read_only: bool = True
    branches: list[SourceBranchOut]


class SourceBranchImportRequest(BaseModel):
    branch_name: str = Field(min_length=1, max_length=255)
    department_id: str
    access_scope: str = "restricted"
    confirm_sensitive_department_access: bool = False

    @field_validator("access_scope")
    @classmethod
    def valid_source_scope(cls, value: str) -> str:
        if value not in ACCESS_SCOPES:
            raise ValueError("invalid access scope")
        return value


class SourceBranchImportOut(BaseModel):
    branch_name: str
    knowledge_base_id: str
    knowledge_base_name: str
    created_knowledge_base: bool
    imported_count: int
    skipped_duplicate_count: int
    unsupported_count: int
    oversized_count: int
    failed_count: int
    job_ids: list[str]
