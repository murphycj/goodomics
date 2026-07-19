# pyright: reportArgumentType=false
"""Authentication, principals, and project capability authorization."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.server.db.models import (
    InstallationStateRecord,
    ProjectMembershipRecord,
    ProjectRolePermissionRecord,
    ProjectRoleRecord,
    UserRecord,
)
from goodomics.server.db.session import SessionDep
from goodomics.server.settings import PasswordSettings, Settings
from goodomics.storage.sqlalchemy import ProjectRecord

PrincipalKind = Literal["local", "anonymous", "user"]
INSTALLATION_STATE_KEY = "installation"

PERMISSIONS = frozenset(
    {
        "project.create",
        "project.read",
        "project.configure",
        "project.members.read",
        "project.members.manage",
        "project.roles.read",
        "project.roles.manage",
        "data.read",
        "data.ingest",
        "data.edit",
        "data.delete",
        "database.read",
        "database.edit",
        "files.read",
        "files.create",
        "files.delete",
        "insight.read",
        "insight.create",
        "insight.edit",
        "insight.delete",
        "insight.execute",
        "report.read",
        "report.create",
        "report.edit",
        "report.delete",
        "report.execute",
        "result.persist",
        "cohort.read",
        "cohort.manage",
        "qc_policy.read",
        "qc_policy.manage",
        "ai.chat",
    }
)

VIEWER_PERMISSIONS = frozenset(
    {
        "project.read",
        "data.read",
        "database.read",
        "files.read",
        "insight.read",
        "insight.execute",
        "report.read",
        "report.execute",
        "cohort.read",
        "qc_policy.read",
        "ai.chat",
    }
)
ANALYST_PERMISSIONS = VIEWER_PERMISSIONS | {
    "insight.create",
    "insight.edit",
    "insight.delete",
    "report.create",
    "report.edit",
    "report.delete",
    "result.persist",
}
DATA_MANAGER_PERMISSIONS = ANALYST_PERMISSIONS | {
    "data.ingest",
    "data.edit",
    "data.delete",
    "database.edit",
    "files.create",
    "files.delete",
    "cohort.manage",
    "qc_policy.manage",
}
OWNER_PERMISSIONS = PERMISSIONS - {"project.create"}

BUILTIN_ROLES: dict[str, frozenset[str]] = {
    "Viewer": VIEWER_PERMISSIONS,
    "Analyst": ANALYST_PERMISSIONS,
    "Data Manager": DATA_MANAGER_PERMISSIONS,
    "Owner": OWNER_PERMISSIONS,
}

_PASSWORD_HASH = PasswordHash.recommended()
current_principal: ContextVar[Principal | None] = ContextVar(
    "goodomics_current_principal", default=None
)


@dataclass(frozen=True)
class Principal:
    """Request-scoped identity used by API, MCP, and project authorization.

    A principal represents either the trusted local identity used when
    authentication is disabled, an authenticated user, or an anonymous caller.
    """

    kind: PrincipalKind
    """Identity category that determines the principal's authentication state."""

    user_id: str | None = None
    """Stable public user identifier for a user principal."""

    user_pk: int | None = None
    """Internal catalog primary key for authorization queries."""

    email: str | None = None
    """Normalized email associated with a user principal."""

    display_name: str | None = None
    """Human-readable name shown for the resolved identity."""

    is_admin: bool = False
    """Whether the principal has installation-administrator authority."""

    must_change_password: bool = False
    """Whether the user must replace an administrator-issued password."""

    @property
    def is_authenticated(self) -> bool:
        """Return whether the principal represents a local or signed-in identity."""

        return self.kind in {"local", "user"}


def normalize_email(email: str) -> str:
    """Normalize an email for identity comparison and uniqueness."""

    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("Enter a valid email address")
    return normalized


def hash_password(
    password: str, password_settings: PasswordSettings | None = None
) -> str:
    """Hash a password with the recommended Argon2id implementation."""

    validate_password(password, password_settings)
    encoded = _PASSWORD_HASH.hash(password)
    if not encoded.startswith("$argon2id$"):
        raise RuntimeError("The configured password hasher is not Argon2id")
    return encoded


def validate_password(
    password: str, password_settings: PasswordSettings | None = None
) -> None:
    """Validate a plaintext password against the configured installation policy."""

    policy = password_settings or PasswordSettings()
    requirements: list[str] = []
    if len(password) < policy.min_length:
        requirements.append(f"be at least {policy.min_length} characters")
    if policy.max_length is not None and len(password) > policy.max_length:
        requirements.append(f"be no more than {policy.max_length} characters")
    if policy.require_uppercase and not any(value.isupper() for value in password):
        requirements.append("contain an uppercase letter")
    if policy.require_lowercase and not any(value.islower() for value in password):
        requirements.append("contain a lowercase letter")
    if policy.require_number and not any(value.isdigit() for value in password):
        requirements.append("contain a number")
    if policy.require_symbol and not any(
        not value.isalnum() and not value.isspace() for value in password
    ):
        requirements.append("contain a symbol")
    if requirements:
        raise ValueError(f"Password must {'; '.join(requirements)}")


def verify_password(password: str, encoded: str) -> tuple[bool, str | None]:
    """Verify a password and return an upgraded hash when parameters changed."""

    try:
        return _PASSWORD_HASH.verify_and_update(password, encoded)
    except (TypeError, ValueError):
        return False, None


def issue_access_token(user: UserRecord, settings: Settings) -> str:
    """Issue a fixed-algorithm, short-lived bearer JWT for a user."""

    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user.user_id,
            "email": user.email,
            "iss": settings.auth.issuer,
            "aud": settings.auth.audience,
            "iat": now,
            "exp": now + timedelta(minutes=settings.auth.token_minutes),
            "auth_version": user.auth_version,
        },
        cast(str, settings.auth.secret),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> dict[str, object]:
    """Decode and validate all security-relevant JWT claims."""

    try:
        payload = jwt.decode(
            token,
            cast(str, settings.auth.secret),
            algorithms=["HS256"],
            audience=settings.auth.audience,
            issuer=settings.auth.issuer,
            options={"require": ["sub", "email", "iat", "exp", "auth_version"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid or expired access token"
        ) from exc
    return cast(dict[str, object], payload)


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str | None = None,
    is_admin: bool = False,
    must_change_password: bool = False,
    password_settings: PasswordSettings | None = None,
) -> UserRecord:
    """Create a normalized user row."""

    normalized = normalize_email(email)
    existing = (
        await session.exec(
            select(UserRecord).where(func.lower(UserRecord.email) == normalized)
        )
    ).first()

    if existing is not None:
        raise ValueError("A user with this email already exists")

    now = datetime.now(UTC)
    user = UserRecord(
        user_id=f"usr_{uuid4().hex[:20]}",
        email=normalized,
        password_hash=hash_password(password, password_settings),
        display_name=(display_name or normalized.split("@", 1)[0]).strip(),
        is_admin=is_admin,
        must_change_password=must_change_password,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.flush()

    return user


async def installation_setup_required(session: AsyncSession) -> bool:
    """Return whether an authenticated installation still needs its first user."""

    state = await session.get(InstallationStateRecord, INSTALLATION_STATE_KEY)

    if state is not None:
        return False

    user_id = (await session.exec(select(UserRecord.id).limit(1))).first()

    return user_id is None


async def complete_installation_setup(
    session: AsyncSession, user: UserRecord
) -> InstallationStateRecord:
    """Permanently close first-run setup for the installation."""

    existing = await session.get(InstallationStateRecord, INSTALLATION_STATE_KEY)

    if existing is not None:
        return existing

    state = InstallationStateRecord(
        state_key=INSTALLATION_STATE_KEY,
        setup_completed_at=datetime.now(UTC),
        setup_completed_by_user_id=user.user_id,
    )

    session.add(state)
    await session.flush()

    return state


async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> UserRecord | None:
    """Verify credentials without revealing which part was invalid."""

    try:
        normalized = normalize_email(email)
    except ValueError:
        return None

    user = (
        await session.exec(
            select(UserRecord).where(func.lower(UserRecord.email) == normalized)
        )
    ).first()

    if user is None or not user.is_active:
        return None

    valid, replacement = verify_password(password, user.password_hash)

    if not valid:
        return None

    if replacement:
        user.password_hash = replacement
        user.updated_at = datetime.now(UTC)
        session.add(user)
        await session.flush()

    return user


async def resolve_principal(request: Request, session: SessionDep) -> Principal:
    """Resolve local, anonymous, or bearer-authenticated request identity."""

    settings: Settings = request.app.state.settings

    if not settings.auth.enabled:
        principal = Principal(kind="local", is_admin=True, display_name="Local user")
        request.state.principal = principal
        current_principal.set(principal)
        return principal

    authorization = request.headers.get("authorization", "")

    if not authorization:
        principal = Principal(kind="anonymous", display_name="Anonymous")
        request.state.principal = principal
        current_principal.set(principal)
        return principal

    # Otherwise, expect a bearer token in the authorization header.
    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    payload = decode_access_token(token, settings)
    user = (
        await session.exec(
            select(UserRecord).where(UserRecord.user_id == str(payload["sub"]))
        )
    ).first()

    if (
        user is None
        or not user.is_active
        or user.email != payload["email"]
        or user.auth_version != payload["auth_version"]
    ):
        raise HTTPException(status_code=401, detail="Access token is no longer valid")

    # Construct a Principal object for the authenticated user.
    principal = Principal(
        kind="user",
        user_id=user.user_id,
        user_pk=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        must_change_password=user.must_change_password,
    )
    request.state.principal = principal
    current_principal.set(principal)

    return principal


async def authorize_api_request(request: Request, session: SessionDep) -> Principal:
    """Resolve identity and centrally gate project-scoped API operations."""

    principal = await resolve_principal(request, session)

    if principal.kind == "local":
        return principal

    path = request.url.path

    if path in {"/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/signup"}:
        return principal

    if path.startswith("/api/v1/auth/"):
        return principal

    # Project creation requires authentication for users.
    if path == "/api/v1/projects" and request.method == "POST":
        if principal.kind != "user":
            raise HTTPException(status_code=401, detail="Authentication required")
        return principal

    # Extract project ID from path, query parameters, or
    # request body for project-scoped operations.
    project_id = request.path_params.get("project_id") or request.query_params.get(
        "project_id"
    )
    if project_id is None and request.method in {"POST", "PATCH"}:
        try:
            body = await request.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("project_id"), str):
            project_id = body["project_id"]

    if project_id is None:
        # Global collection endpoints perform authorized-project filtering in
        # their handlers. Direct legacy-ID endpoints resolve ownership there.
        return principal

    project = (
        await session.exec(
            select(ProjectRecord).where(ProjectRecord.project_id == project_id)
        )
    ).first()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    permission = _request_permission(request.method, path)
    await require_project_permission(request, session, project, permission)

    return principal


def _request_permission(method: str, path: str) -> str:
    """Map API operations to code-owned capabilities."""

    mutation = method in {"POST", "PATCH", "PUT", "DELETE"}

    if "/members" in path:
        return "project.members.manage" if mutation else "project.members.read"

    if "/roles" in path:
        return "project.roles.manage" if mutation else "project.roles.read"

    if "/qc-policies" in path:
        return "qc_policy.manage" if mutation else "qc_policy.read"

    if "/sample-groups" in path or "/sample-sets" in path:
        return "cohort.manage" if mutation else "cohort.read"

    if "/database" in path:
        return "database.edit" if mutation else "database.read"

    if "/files" in path:
        if method == "POST":
            return "files.create"
        return "files.delete" if method == "DELETE" else "files.read"

    if "/insights" in path:
        if path.endswith("/execute") or path.endswith("/validate"):
            return "insight.execute"
        return {
            "POST": "insight.create",
            "PATCH": "insight.edit",
            "DELETE": "insight.delete",
        }.get(method, "insight.read")

    if "/reports" in path:
        if path.endswith("/execute"):
            return "report.execute"
        return {
            "POST": "report.create",
            "PATCH": "report.edit",
            "DELETE": "report.delete",
        }.get(method, "report.read")

    if path.endswith("/ai/chat"):
        return "ai.chat"

    if "/runs" in path or "/samples" in path or "/contracts" in path:
        return (
            "data.ingest"
            if method == "POST"
            else "data.edit"
            if mutation
            else "data.read"
        )
    if method == "PATCH":
        return "project.configure"

    return "project.read"


async def project_permissions(
    session: AsyncSession,
    principal: Principal,
    project: ProjectRecord,
    settings: Settings,
) -> set[str]:
    """Load current project capabilities from SQL for immediate role updates."""

    if principal.kind == "local" or principal.is_admin:
        return set(PERMISSIONS)

    if principal.kind == "anonymous":
        return (
            set(settings.anonymous.permissions)
            if project.visibility == "public"
            else set()
        )

    rows = (
        await session.exec(
            select(ProjectRolePermissionRecord.permission)
            .join(
                ProjectMembershipRecord,
                ProjectMembershipRecord.role_id == ProjectRolePermissionRecord.role_id,
            )
            .where(
                ProjectMembershipRecord.project_id == project.id,
                ProjectMembershipRecord.user_id == principal.user_pk,
            )
        )
    ).all()

    return {str(row) for row in rows}


async def authorized_project_pks(
    session: AsyncSession, principal: Principal, settings: Settings
) -> set[int] | None:
    """Return visible project primary keys, or ``None`` for unrestricted access."""

    if principal.kind == "local" or principal.is_admin:
        return None

    if principal.kind == "anonymous":
        rows = (
            await session.exec(
                select(ProjectRecord.id).where(ProjectRecord.visibility == "public")
            )
        ).all()
    else:
        member_rows = (
            await session.exec(
                select(ProjectMembershipRecord.project_id).where(
                    ProjectMembershipRecord.user_id == principal.user_pk
                )
            )
        ).all()
        public_rows = (
            await session.exec(
                select(ProjectRecord.id).where(ProjectRecord.visibility == "public")
            )
        ).all()
        rows = [*member_rows, *public_rows]

    return {int(value) for value in rows if value is not None}


async def require_project_permission(
    request: Request,
    session: AsyncSession,
    project: ProjectRecord,
    permission: str,
) -> None:
    """Raise 403 unless the effective principal has a project capability."""

    principal = getattr(request.state, "principal", None)

    if principal is None:
        principal = await resolve_principal(request, session)

    permissions = await project_permissions(
        session, principal, project, request.app.state.settings
    )

    if permission not in permissions:
        if principal.kind == "anonymous" and project.visibility != "public":
            raise HTTPException(status_code=401, detail="Authentication required")
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")


async def seed_project_roles(
    session: AsyncSession, project: ProjectRecord
) -> dict[str, ProjectRoleRecord]:
    """Ensure the four editable built-in permission bundles exist."""

    existing = (
        await session.exec(
            select(ProjectRoleRecord).where(ProjectRoleRecord.project_id == project.id)
        )
    ).all()

    by_name = {role.name: role for role in existing}

    for name, permissions in BUILTIN_ROLES.items():
        role = by_name.get(name)

        if role is None:
            role = ProjectRoleRecord(
                role_id=f"rol_{uuid4().hex[:20]}",
                project_id=cast(int, project.id),
                name=name,
                description=f"Built-in {name} role",
                is_builtin=True,
            )
            session.add(role)
            await session.flush()
            by_name[name] = role

        current = set(
            (
                await session.exec(
                    select(ProjectRolePermissionRecord.permission).where(
                        ProjectRolePermissionRecord.role_id == role.id
                    )
                )
            ).all()
        )

        session.add_all(
            ProjectRolePermissionRecord(role_id=cast(int, role.id), permission=value)
            for value in sorted(permissions - current)
        )

    await session.flush()

    return by_name
