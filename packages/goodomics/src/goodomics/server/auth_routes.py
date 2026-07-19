# pyright: reportArgumentType=false
"""HTTP session, installation-user, and project-membership endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from goodomics.server.auth import (
    PERMISSIONS,
    Principal,
    authenticate_user,
    complete_installation_setup,
    create_user,
    hash_password,
    installation_setup_required,
    issue_access_token,
    normalize_email,
    project_permissions,
    require_project_permission,
    resolve_principal,
    seed_project_roles,
    verify_password,
)
from goodomics.server.db.models import (
    ProjectMembershipRecord,
    ProjectRolePermissionRecord,
    ProjectRoleRecord,
    UserRecord,
)
from goodomics.server.db.session import get_session
from goodomics.server.rate_limits import client_ip
from goodomics.storage.sqlalchemy import ProjectRecord

router = APIRouter(prefix="/api/v1", dependencies=[Depends(get_session)])


class Credentials(BaseModel):
    """Email and password credentials supplied to an authentication operation."""

    email: str
    password: str


class SignupRequest(Credentials):
    """Credentials and optional profile name for public account creation."""

    display_name: str | None = None


class SetupRequest(SignupRequest):
    """First-administrator details submitted during installation setup."""

    pass


class PasswordPolicyRead(BaseModel):
    """Client-visible password length and composition requirements."""

    min_length: int
    max_length: int | None
    require_uppercase: bool
    require_lowercase: bool
    require_number: bool
    require_symbol: bool


class SetupStatusRead(BaseModel):
    """Authentication, first-run setup, and password-policy status."""

    auth_enabled: bool
    signup_enabled: bool
    setup_required: bool
    password_policy: PasswordPolicyRead


class ChangePasswordRequest(BaseModel):
    """Current and replacement passwords for an authenticated user."""

    current_password: str
    new_password: str


class ProfilePatchRequest(BaseModel):
    """Optional profile fields that the signed-in user may update."""

    email: str | None = None
    display_name: str | None = None


class TokenRead(BaseModel):
    """Bearer access token and its lifetime returned after authentication."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreateRequest(BaseModel):
    """Administrator-supplied fields for creating an installation user."""

    email: str
    password: str
    display_name: str | None = None
    is_admin: bool = False
    must_change_password: bool = True


class UserPatchRequest(BaseModel):
    """Administrator-controlled updates to an installation user."""

    email: str | None = None
    display_name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    password: str | None = None
    must_change_password: bool | None = None


class UserRead(BaseModel):
    """Public administrator view of an installation user."""

    user_id: str
    email: str
    display_name: str
    is_active: bool
    is_admin: bool
    must_change_password: bool
    created_at: datetime


class RoleCreateRequest(BaseModel):
    """Name, description, and permissions for a new project role."""

    name: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class RolePatchRequest(BaseModel):
    """Optional project-role fields to replace during an update."""

    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class RoleRead(BaseModel):
    """Project role metadata and its resolved permission set."""

    role_id: str
    name: str
    description: str | None
    is_builtin: bool
    permissions: list[str]


class MembershipCreateRequest(BaseModel):
    """User and role references for a new project membership."""

    user_id: str
    role_id: str


class MembershipPatchRequest(BaseModel):
    """Replacement role for an existing project membership."""

    role_id: str


class MembershipRead(BaseModel):
    """Project membership with embedded user and role details."""

    membership_id: str
    user: UserRead
    role: RoleRead


class AdminMembershipRead(BaseModel):
    """Cross-project membership summary shown to installation administrators."""

    membership_id: str
    project_id: str
    project_name: str
    role: RoleRead


class MeRead(BaseModel):
    """Current identity, membership, permission, and setup context."""

    principal: dict[str, Any]
    memberships: list[dict[str, Any]]
    permissions: dict[str, list[str]]
    auth_enabled: bool
    signup_enabled: bool
    setup_required: bool
    password_policy: PasswordPolicyRead


@router.post("/auth/login", response_model=TokenRead)
async def login(payload: Credentials, request: Request) -> TokenRead:
    """Authenticate an active user under login rate limits and issue a token."""

    settings = request.app.state.settings

    if not settings.auth.enabled:
        raise HTTPException(status_code=404, detail="Authentication is disabled")

    # Enforce login rate limiting before proceeding
    await request.app.state.rate_limiter.check(
        "login", client_ip(request, settings), settings.rate_limits.login
    )

    async with _session_context(request) as session:
        user = await authenticate_user(session, payload.email, payload.password)

        if user is None:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        token = issue_access_token(user, settings)

        await session.commit()

    return TokenRead(access_token=token, expires_in=settings.auth.token_minutes * 60)


@router.post("/auth/signup", response_model=TokenRead, status_code=201)
async def signup(payload: SignupRequest, request: Request) -> TokenRead:
    """Create and authenticate a user when public signup is enabled."""

    settings = request.app.state.settings

    if not settings.auth.enabled or not settings.auth.signup_enabled:
        raise HTTPException(status_code=404, detail="Public signup is disabled")

    async with _session_context(request) as session:
        if await installation_setup_required(session):
            raise HTTPException(
                status_code=409,
                detail="Complete installation setup before enabling public signup",
            )
        try:
            user = await create_user(
                session,
                email=payload.email,
                password=payload.password,
                display_name=payload.display_name,
                password_settings=settings.auth.password,
            )
            token = issue_access_token(user, settings)
            await session.commit()
        except ValueError as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return TokenRead(access_token=token, expires_in=settings.auth.token_minutes * 60)


@router.get("/auth/setup", response_model=SetupStatusRead)
async def setup_status(request: Request) -> SetupStatusRead:
    """Report whether authentication and first-run setup are active."""

    settings = request.app.state.settings
    password_policy = PasswordPolicyRead(**settings.auth.password.model_dump())

    if not settings.auth.enabled:
        return SetupStatusRead(
            auth_enabled=False,
            signup_enabled=False,
            setup_required=False,
            password_policy=password_policy,
        )
    async with _session_context(request) as session:
        required = await installation_setup_required(session)

    return SetupStatusRead(
        auth_enabled=True,
        signup_enabled=settings.auth.signup_enabled,
        setup_required=required,
        password_policy=password_policy,
    )


@router.post("/auth/setup", response_model=TokenRead, status_code=201)
async def setup(payload: SetupRequest, request: Request) -> TokenRead:
    """Create and authenticate the first installation administrator once."""

    settings = request.app.state.settings

    if not settings.auth.enabled:
        raise HTTPException(status_code=404, detail="Authentication is disabled")

    await request.app.state.rate_limiter.check(
        "login", client_ip(request, settings), settings.rate_limits.login
    )

    async with _session_context(request) as session:
        if not await installation_setup_required(session):
            raise HTTPException(
                status_code=409, detail="Installation setup is already complete"
            )
        try:
            user = await create_user(
                session,
                email=payload.email,
                password=payload.password,
                display_name=payload.display_name,
                is_admin=True,
                password_settings=settings.auth.password,
            )
            await complete_installation_setup(session, user)
            token = issue_access_token(user, settings)
            await session.commit()
        except ValueError as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409, detail="Installation setup is already complete"
            ) from exc

    return TokenRead(access_token=token, expires_in=settings.auth.token_minutes * 60)


@router.get("/auth/me", response_model=MeRead)
async def me(request: Request) -> MeRead:
    """Return the current principal and its project authorization context."""

    principal = await resolve_principal(request, _session(request))
    status = await setup_status(request)

    if principal.kind == "anonymous":
        # Load all public projects for anonymous users to
        # determine their project-scoped permissions.
        async with _session_context(request) as session:
            projects = (
                await session.exec(
                    select(ProjectRecord).where(ProjectRecord.visibility == "public")
                )
            ).all()
        anonymous_permissions = sorted(request.app.state.settings.anonymous.permissions)

        return MeRead(
            principal=_principal_dict(principal),
            memberships=[],
            permissions={
                project.project_id: anonymous_permissions for project in projects
            },
            auth_enabled=status.auth_enabled,
            signup_enabled=status.signup_enabled,
            setup_required=status.setup_required,
            password_policy=status.password_policy,
        )

    if principal.kind == "local":
        return MeRead(
            principal=_principal_dict(principal),
            memberships=[],
            permissions={"*": sorted(PERMISSIONS)},
            auth_enabled=status.auth_enabled,
            signup_enabled=status.signup_enabled,
            setup_required=status.setup_required,
            password_policy=status.password_policy,
        )

    async with _session_context(request) as session:
        rows = (
            await session.exec(
                select(ProjectMembershipRecord, ProjectRecord, ProjectRoleRecord)
                .join(
                    ProjectRecord,
                    ProjectRecord.id == ProjectMembershipRecord.project_id,
                )
                .join(
                    ProjectRoleRecord,
                    ProjectRoleRecord.id == ProjectMembershipRecord.role_id,
                )
                .where(ProjectMembershipRecord.user_id == principal.user_pk)
            )
        ).all()

        permission_map = {
            project.project_id: sorted(
                await project_permissions(
                    session, principal, project, request.app.state.settings
                )
            )
            for _, project, _ in rows
        }

    return MeRead(
        principal=_principal_dict(principal),
        memberships=[
            {
                "membership_id": membership.membership_id,
                "project_id": project.project_id,
                "project_name": project.name,
                "role_id": role.role_id,
                "role_name": role.name,
            }
            for membership, project, role in rows
        ],
        permissions=permission_map,
        auth_enabled=status.auth_enabled,
        signup_enabled=status.signup_enabled,
        setup_required=status.setup_required,
        password_policy=status.password_policy,
    )


@router.post("/auth/change-password", status_code=204)
async def change_password(payload: ChangePasswordRequest, request: Request) -> None:
    """Replace the signed-in user's password and invalidate existing tokens."""

    principal = await _require_user(request)

    async with _session_context(request) as session:
        user = await session.get(UserRecord, principal.user_pk)
        if (
            user is None
            or not verify_password(payload.current_password, user.password_hash)[0]
        ):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        try:
            user.password_hash = hash_password(
                payload.new_password, request.app.state.settings.auth.password
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        user.auth_version += 1
        user.must_change_password = False
        user.updated_at = datetime.now(UTC)
        session.add(user)
        await session.commit()


@router.patch("/auth/me", response_model=TokenRead)
async def update_profile(payload: ProfilePatchRequest, request: Request) -> TokenRead:
    """Update the signed-in user's profile and return a refreshed token."""

    principal = await _require_user(request)
    settings = request.app.state.settings

    async with _session_context(request) as session:
        user = await session.get(UserRecord, principal.user_pk)

        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if payload.email is not None:
            try:
                normalized = normalize_email(payload.email)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            # Check if another user already has this email address
            existing = (
                await session.exec(
                    select(UserRecord).where(
                        func.lower(UserRecord.email) == normalized,
                        UserRecord.id != user.id,
                    )
                )
            ).first()

            if existing is not None:
                raise HTTPException(
                    status_code=400,
                    detail="A user with this email already exists",
                )

            # Update the user's email if it has changed
            if normalized != user.email:
                user.email = normalized
                user.auth_version += 1

        if payload.display_name is not None:
            display_name = payload.display_name.strip()
            if not display_name:
                raise HTTPException(
                    status_code=400, detail="Display name cannot be empty"
                )
            user.display_name = display_name

        user.updated_at = datetime.now(UTC)
        session.add(user)

        try:
            await session.commit()
            await session.refresh(user)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=400, detail="A user with this email already exists"
            ) from exc
        token = issue_access_token(user, settings)

    return TokenRead(access_token=token, expires_in=settings.auth.token_minutes * 60)


@router.get("/users", response_model=list[UserRead])
async def list_users(request: Request) -> list[UserRead]:
    """List installation users for an authenticated administrator."""

    await _require_admin(request)
    async with _session_context(request) as session:
        rows = (await session.exec(select(UserRecord).order_by(UserRecord.email))).all()

    return [_user_read(user) for user in rows]


@router.post("/users", response_model=UserRead, status_code=201)
async def add_user(payload: UserCreateRequest, request: Request) -> UserRead:
    """Create an installation user as an authenticated administrator."""

    await _require_admin(request)
    async with _session_context(request) as session:
        try:
            user = await create_user(
                session,
                password_settings=request.app.state.settings.auth.password,
                **payload.model_dump(),
            )
            await session.commit()
            await session.refresh(user)
        except ValueError as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _user_read(user)


@router.get("/users/{user_id}/memberships", response_model=list[AdminMembershipRead])
async def list_user_memberships(
    user_id: str, request: Request
) -> list[AdminMembershipRead]:
    """List one user's memberships across projects for an administrator."""

    await _require_admin(request)

    async with _session_context(request) as session:
        user = (
            await session.exec(select(UserRecord).where(UserRecord.user_id == user_id))
        ).first()

        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        rows = (
            await session.exec(
                select(
                    ProjectMembershipRecord,
                    ProjectRecord,
                    ProjectRoleRecord,
                )
                .join(
                    ProjectRecord,
                    ProjectRecord.id == ProjectMembershipRecord.project_id,
                )
                .join(
                    ProjectRoleRecord,
                    ProjectRoleRecord.id == ProjectMembershipRecord.role_id,
                )
                .where(ProjectMembershipRecord.user_id == user.id)
                .order_by(ProjectRecord.name)
            )
        ).all()

        return [
            AdminMembershipRead(
                membership_id=membership.membership_id,
                project_id=project.project_id,
                project_name=project.name,
                role=await _role_read(session, role),
            )
            for membership, project, role in rows
        ]


@router.patch("/users/{user_id}", response_model=UserRead)
async def patch_user(
    user_id: str, payload: UserPatchRequest, request: Request
) -> UserRead:
    """Update an installation user while preserving an active administrator."""

    await _require_admin(request)

    async with _session_context(request) as session:
        user = (
            await session.exec(select(UserRecord).where(UserRecord.user_id == user_id))
        ).first()

        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        updates = payload.model_dump(exclude_unset=True)

        # Determine if the update would remove the last active administrator.
        removes_active_admin = (
            user.is_admin
            and user.is_active
            and (updates.get("is_admin") is False or updates.get("is_active") is False)
        )

        if removes_active_admin:
            another_active_admin = (
                await session.exec(
                    select(UserRecord.id).where(
                        UserRecord.id != user.id,
                        UserRecord.is_admin,
                        UserRecord.is_active,
                    )
                )
            ).first()

            if another_active_admin is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The installation must keep at least one active administrator"
                    ),
                )

        password = updates.pop("password", None)
        email = updates.pop("email", None)
        display_name = updates.pop("display_name", None)

        # Update the password if provided, hashing it appropriately.
        if password is not None:
            try:
                user.password_hash = hash_password(
                    password, request.app.state.settings.auth.password
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            user.auth_version += 1

        # Update the email if provided, ensuring uniqueness and normalization.
        if email is not None:
            try:
                normalized = normalize_email(email)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            existing = (
                await session.exec(
                    select(UserRecord).where(
                        func.lower(UserRecord.email) == normalized,
                        UserRecord.id != user.id,
                    )
                )
            ).first()

            if existing is not None:
                raise HTTPException(
                    status_code=400,
                    detail="A user with this email already exists",
                )
            if normalized != user.email:
                user.email = normalized
                user.auth_version += 1

        # Update the display name if provided, ensuring it is not empty.
        if display_name is not None:
            normalized_name = display_name.strip()
            if not normalized_name:
                raise HTTPException(
                    status_code=400, detail="Display name cannot be empty"
                )
            user.display_name = normalized_name

        # Apply any other updates to the user record.
        for key, value in updates.items():
            setattr(user, key, value)
        user.updated_at = datetime.now(UTC)
        session.add(user)

        try:
            await session.commit()
            await session.refresh(user)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=400, detail="A user with this email already exists"
            ) from exc

    return _user_read(user)


@router.get("/projects/{project_id}/roles", response_model=list[RoleRead])
async def list_roles(project_id: str, request: Request) -> list[RoleRead]:
    """List seeded and custom roles visible within a project."""

    project = await _project(request, project_id)
    await require_project_permission(
        request, _session(request), project, "project.roles.read"
    )
    async with _session_context(request) as session:
        await seed_project_roles(session, project)
        await session.commit()
        roles = (
            await session.exec(
                select(ProjectRoleRecord).where(
                    ProjectRoleRecord.project_id == project.id
                )
            )
        ).all()

        return [await _role_read(session, role) for role in roles]


@router.post("/projects/{project_id}/roles", response_model=RoleRead, status_code=201)
async def add_role(
    project_id: str, payload: RoleCreateRequest, request: Request
) -> RoleRead:
    """Create a custom project role with validated permissions."""

    project = await _project(request, project_id)
    await require_project_permission(
        request, _session(request), project, "project.roles.manage"
    )
    _validate_permissions(payload.permissions)
    async with _session_context(request) as session:
        role = ProjectRoleRecord(
            role_id=f"rol_{uuid4().hex[:20]}",
            project_id=cast(int, project.id),
            name=payload.name.strip(),
            description=payload.description,
        )
        session.add(role)
        await session.flush()
        session.add_all(
            ProjectRolePermissionRecord(role_id=cast(int, role.id), permission=value)
            for value in sorted(set(payload.permissions))
        )
        await session.commit()
        await session.refresh(role)

        return await _role_read(session, role)


@router.patch("/projects/{project_id}/roles/{role_id}", response_model=RoleRead)
async def patch_role(
    project_id: str, role_id: str, payload: RolePatchRequest, request: Request
) -> RoleRead:
    """Update a project role and replace permissions when supplied."""

    project = await _project(request, project_id)
    await require_project_permission(
        request, _session(request), project, "project.roles.manage"
    )

    async with _session_context(request) as session:
        role = await _role(session, project, role_id)
        if payload.name is not None:
            role.name = payload.name.strip()
        if payload.description is not None:
            role.description = payload.description
        if payload.permissions is not None:
            _validate_permissions(payload.permissions)
            await session.exec(
                delete(ProjectRolePermissionRecord).where(
                    ProjectRolePermissionRecord.role_id == role.id
                )
            )
            session.add_all(
                ProjectRolePermissionRecord(
                    role_id=cast(int, role.id), permission=value
                )
                for value in sorted(set(payload.permissions))
            )
        session.add(role)
        await session.commit()

        return await _role_read(session, role)


@router.get("/projects/{project_id}/members", response_model=list[MembershipRead])
async def list_members(project_id: str, request: Request) -> list[MembershipRead]:
    """List users and roles assigned to a project."""

    project = await _project(request, project_id)
    await require_project_permission(
        request, _session(request), project, "project.members.read"
    )

    async with _session_context(request) as session:
        rows = (
            await session.exec(
                select(ProjectMembershipRecord, UserRecord, ProjectRoleRecord)
                .join(UserRecord, UserRecord.id == ProjectMembershipRecord.user_id)
                .join(
                    ProjectRoleRecord,
                    ProjectRoleRecord.id == ProjectMembershipRecord.role_id,
                )
                .where(ProjectMembershipRecord.project_id == project.id)
            )
        ).all()

        return [
            MembershipRead(
                membership_id=membership.membership_id,
                user=_user_read(user),
                role=await _role_read(session, role),
            )
            for membership, user, role in rows
        ]


@router.post(
    "/projects/{project_id}/members", response_model=MembershipRead, status_code=201
)
async def add_member(
    project_id: str, payload: MembershipCreateRequest, request: Request
) -> MembershipRead:
    """Assign an installation user to a project role."""

    project = await _project(request, project_id)
    await require_project_permission(
        request, _session(request), project, "project.members.manage"
    )

    async with _session_context(request) as session:
        user = (
            await session.exec(
                select(UserRecord).where(UserRecord.user_id == payload.user_id)
            )
        ).first()
        role = await _role(session, project, payload.role_id)

        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        membership = ProjectMembershipRecord(
            membership_id=f"mem_{uuid4().hex[:20]}",
            project_id=cast(int, project.id),
            user_id=cast(int, user.id),
            role_id=cast(int, role.id),
            created_at=datetime.now(UTC),
        )
        session.add(membership)
        await session.commit()
        await session.refresh(membership)
        await session.refresh(user)
        await session.refresh(role)

        return MembershipRead(
            membership_id=membership.membership_id,
            user=_user_read(user),
            role=await _role_read(session, role),
        )


@router.patch(
    "/projects/{project_id}/members/{membership_id}", response_model=MembershipRead
)
async def patch_member(
    project_id: str,
    membership_id: str,
    payload: MembershipPatchRequest,
    request: Request,
) -> MembershipRead:
    """Replace the project role assigned to an existing membership."""

    project = await _project(request, project_id)
    await require_project_permission(
        request, _session(request), project, "project.members.manage"
    )

    async with _session_context(request) as session:
        membership = await _membership(session, project, membership_id)
        role = await _role(session, project, payload.role_id)
        membership.role_id = cast(int, role.id)
        session.add(membership)
        await session.commit()
        await session.refresh(membership)
        await session.refresh(role)
        user = await session.get(UserRecord, membership.user_id)

        return MembershipRead(
            membership_id=membership.membership_id,
            user=_user_read(cast(UserRecord, user)),
            role=await _role_read(session, role),
        )


@router.delete("/projects/{project_id}/members/{membership_id}", status_code=204)
async def delete_member(project_id: str, membership_id: str, request: Request) -> None:
    """Remove an existing membership from a project."""

    project = await _project(request, project_id)
    await require_project_permission(
        request, _session(request), project, "project.members.manage"
    )
    async with _session_context(request) as session:
        membership = await _membership(session, project, membership_id)
        await session.delete(membership)
        await session.commit()


async def _require_user(request: Request) -> Principal:
    """Resolve and require a signed-in installation user."""

    principal = await resolve_principal(request, _session(request))
    if principal.kind != "user":
        raise HTTPException(status_code=401, detail="Authentication required")

    return principal


async def _require_admin(request: Request) -> Principal:
    """Resolve and require an installation administrator."""

    principal = await _require_user(request)
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Installation admin required")

    return principal


async def _project(request: Request, project_id: str) -> ProjectRecord:
    """Load a project by public identifier or raise an HTTP not-found error."""

    async with _session_context(request) as session:
        project = (
            await session.exec(
                select(ProjectRecord).where(ProjectRecord.project_id == project_id)
            )
        ).first()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


def _session(request: Request) -> AsyncSession:
    """Return the FastAPI request-scoped SQL session."""

    return cast(AsyncSession, request.state.db_session)


@asynccontextmanager
async def _session_context(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield the request session without closing it before response completion."""

    yield _session(request)


async def _role(
    session: AsyncSession, project: ProjectRecord, role_id: str
) -> ProjectRoleRecord:
    """Load a role belonging to a project or raise an HTTP not-found error."""

    role = (
        await session.exec(
            select(ProjectRoleRecord).where(
                ProjectRoleRecord.project_id == project.id,
                ProjectRoleRecord.role_id == role_id,
            )
        )
    ).first()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


async def _membership(
    session: AsyncSession, project: ProjectRecord, membership_id: str
) -> ProjectMembershipRecord:
    """Load a project membership or raise an HTTP not-found error."""

    membership = (
        await session.exec(
            select(ProjectMembershipRecord).where(
                ProjectMembershipRecord.project_id == project.id,
                ProjectMembershipRecord.membership_id == membership_id,
            )
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    return membership


async def _role_read(session: AsyncSession, role: ProjectRoleRecord) -> RoleRead:
    """Build a role response with permissions loaded in stable order."""

    permissions = (
        await session.exec(
            select(ProjectRolePermissionRecord.permission).where(
                ProjectRolePermissionRecord.role_id == role.id
            )
        )
    ).all()
    return RoleRead(
        role_id=role.role_id,
        name=role.name,
        description=role.description,
        is_builtin=role.is_builtin,
        permissions=sorted(str(value) for value in permissions),
    )


def _user_read(user: UserRecord) -> UserRead:
    """Convert a persisted user record into its public response model."""

    return UserRead.model_validate(user, from_attributes=True)


def _principal_dict(principal: Principal) -> dict[str, Any]:
    """Serialize a resolved principal for the current-session response."""

    return {
        "kind": principal.kind,
        "user_id": principal.user_id,
        "email": principal.email,
        "display_name": principal.display_name,
        "is_admin": principal.is_admin,
        "must_change_password": principal.must_change_password,
        "is_authenticated": principal.is_authenticated,
    }


def _validate_permissions(permissions: list[str]) -> None:
    """Reject permission identifiers outside the supported capability set."""

    invalid = set(permissions) - PERMISSIONS
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown permissions: {', '.join(sorted(invalid))}",
        )
