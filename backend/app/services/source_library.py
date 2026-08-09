"""Read-only discovery of first-level branches in the enterprise source library."""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.storage import _ALLOWED_EXT


_SENSITIVE_TERMS = (
    "简历",
    "合同",
    "人事",
    "员工",
    "薪酬",
    "法务",
    "财务",
    "客户",
)
_SKIP_DIRECTORIES = {".git", ".idea", "__pycache__", "_tmp", "_临时", "_导入"}


class SourceLibraryError(ValueError):
    """Raised when a requested source branch cannot be proven safe."""


@dataclass(frozen=True)
class SourceFile:
    path: Path
    display_name: str
    extension: str
    size_bytes: int


@dataclass
class SourceBranchSnapshot:
    name: str
    total_file_count: int = 0
    supported_file_count: int = 0
    importable_file_count: int = 0
    unsupported_file_count: int = 0
    oversized_file_count: int = 0
    total_size_bytes: int = 0
    extension_counts: dict[str, int] = field(default_factory=dict)
    last_modified_at: datetime | None = None
    sensitive: bool = False
    recommended_access_scope: str = "department"
    truncated: bool = False
    files: list[SourceFile] = field(default_factory=list, repr=False)


def configured_source_root() -> Path:
    return settings.knowledge_source_path


def available_source_root() -> Path | None:
    try:
        root = configured_source_root().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return root if root.is_dir() else None


def _safe_branch(root: Path, branch_name: str) -> Path:
    name = branch_name.strip()
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or Path(name).name != name
    ):
        raise SourceLibraryError("分支名称无效")
    raw = root / name
    if raw.is_symlink():
        raise SourceLibraryError("不允许访问符号链接分支")
    try:
        branch = raw.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SourceLibraryError("总资料库分支不存在") from exc
    if branch.parent != root or not branch.is_dir():
        raise SourceLibraryError("分支必须是总资料库的一级目录")
    return branch


def _safe_display_name(branch: Path, path: Path) -> str:
    relative = path.relative_to(branch).as_posix()
    if len(relative) <= 512:
        return relative
    suffix = path.name[-480:]
    return f"…/{suffix}"[:512]


def scan_branch(root: Path, branch_name: str) -> SourceBranchSnapshot:
    branch = _safe_branch(root, branch_name)
    sensitive = any(term in branch.name for term in _SENSITIVE_TERMS)
    snapshot = SourceBranchSnapshot(
        name=branch.name,
        sensitive=sensitive,
        recommended_access_scope="restricted" if sensitive else "department",
    )
    extensions: Counter[str] = Counter()
    newest_mtime = 0.0
    limit = max(1, settings.knowledge_source_scan_limit)

    stop = False
    for current, directory_names, file_names in os.walk(branch, followlinks=False):
        current_path = Path(current)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in _SKIP_DIRECTORIES
            and not name.startswith(".")
            and not (current_path / name).is_symlink()
        )
        for filename in sorted(file_names):
            if snapshot.total_file_count >= limit:
                snapshot.truncated = True
                stop = True
                break
            raw = current_path / filename
            if raw.is_symlink():
                continue
            try:
                path = raw.resolve(strict=True)
                if branch not in path.parents or not path.is_file():
                    continue
                stat = path.stat()
            except (OSError, RuntimeError):
                continue

            snapshot.total_file_count += 1
            snapshot.total_size_bytes += stat.st_size
            newest_mtime = max(newest_mtime, stat.st_mtime)
            ext = path.suffix.lower()
            extensions[ext or "[无扩展名]"] += 1
            if ext not in _ALLOWED_EXT:
                snapshot.unsupported_file_count += 1
                continue
            snapshot.supported_file_count += 1
            if stat.st_size > settings.max_file_bytes:
                snapshot.oversized_file_count += 1
                continue
            snapshot.importable_file_count += 1
            snapshot.files.append(
                SourceFile(
                    path=path,
                    display_name=_safe_display_name(branch, path),
                    extension=ext,
                    size_bytes=stat.st_size,
                )
            )
        if stop:
            break

    snapshot.extension_counts = dict(sorted(extensions.items()))
    if newest_mtime:
        snapshot.last_modified_at = datetime.fromtimestamp(newest_mtime, tz=timezone.utc)
    return snapshot


def scan_source_library() -> tuple[Path, bool, list[SourceBranchSnapshot]]:
    configured = configured_source_root()
    root = available_source_root()
    if root is None:
        return configured, False, []
    branches: list[SourceBranchSnapshot] = []
    try:
        candidates = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return configured, False, []
    for path in candidates:
        if (
            not path.is_dir()
            or path.is_symlink()
            or path.name.startswith(".")
            or path.name in _SKIP_DIRECTORIES
        ):
            continue
        branches.append(scan_branch(root, path.name))
    return root, True, branches
