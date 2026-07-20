from __future__ import annotations

import asyncio
import io
import tomllib
from importlib.resources import files
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from goodomics.projects import DEFAULT_PROJECT_ID
from goodomics.server.app import create_app
from goodomics.server.auth import create_user, hash_password, verify_password
from goodomics.server.db.models import UserRecord
from goodomics.server.settings import (
    AnalyticsSettings,
    AuthSettings,
    DatabaseSettings,
    PasswordSettings,
    Settings,
    StorageLocationSettings,
    StorageSettings,
    ensure_config_file,
    load_settings,
)
from goodomics.storage.files import FilesystemFileStore, S3FileStore
from goodomics.storage.sqlalchemy import initialized_store
from sqlmodel import delete


def _secured_settings(tmp_path: Path) -> Settings:
    return Settings(
        database=DatabaseSettings(url=f"sqlite+aiosqlite:///{tmp_path / 'secured.db'}"),
        analytics=AnalyticsSettings(root=str(tmp_path / "analytics")),
        auth=AuthSettings(
            enabled=True, secret="a-secure-test-secret-of-adequate-length"
        ),
        storage=StorageSettings(
            locations={
                "default": StorageLocationSettings(
                    driver="filesystem", root=str(tmp_path / "files")
                )
            }
        ),
    )


def _create_user(settings: Settings, *, admin: bool = False) -> None:
    async def create() -> None:
        async with (
            initialized_store(settings.database_url) as store,
            store.session() as session,
        ):
            await create_user(
                session,
                email="ADMIN@Example.org" if admin else "user@example.org",
                password="correct horse battery staple",
                is_admin=admin,
            )
            await session.commit()

    asyncio.run(create())


def test_argon2id_hash_and_verification() -> None:
    encoded = hash_password("abc123")

    assert encoded.startswith("$argon2id$")
    assert verify_password("abc123", encoded)[0]
    assert not verify_password("incorrect password", encoded)[0]
    with pytest.raises(ValueError, match="at least 6 characters"):
        hash_password("short")


def test_configurable_password_composition_policy() -> None:
    policy = PasswordSettings(
        min_length=6,
        max_length=12,
        require_uppercase=True,
        require_lowercase=True,
        require_number=True,
        require_symbol=True,
    )

    assert hash_password("Valid1!", policy).startswith("$argon2id$")
    with pytest.raises(ValueError, match="uppercase"):
        hash_password("invalid1!", policy)
    with pytest.raises(ValueError, match="no more than 12"):
        hash_password("WayTooLong123!", policy)
    with pytest.raises(ValueError, match="max_length"):
        PasswordSettings(min_length=8, max_length=7)


def test_auth_disabled_stays_unrestricted_without_secret(tmp_path: Path) -> None:
    settings = Settings(
        database=DatabaseSettings(url=f"sqlite+aiosqlite:///{tmp_path / 'local.db'}")
    )

    with TestClient(create_app(settings)) as client:
        me = client.get("/api/v1/auth/me").json()
        assert me["principal"]["kind"] == "local"
        assert not me["auth_enabled"]
        assert not me["setup_required"]
        assert (
            client.post(
                "/api/v1/auth/setup",
                json={
                    "email": "owner@example.org",
                    "password": "abc123",
                },
            ).status_code
            == 404
        )
        assert (
            client.post("/api/v1/projects", json={"name": "Local"}).status_code == 201
        )


def test_anonymous_session_exposes_public_permissions_and_disabled_signup(
    tmp_path: Path,
) -> None:
    """Expose public-project capabilities while rejecting disabled signup."""

    settings = _secured_settings(tmp_path)

    async def expose_default_project() -> None:
        """Create the default project and make it visible to anonymous callers."""

        async with initialized_store(settings.database_url) as store:
            await store.ensure_default_project()
            await store.set_project_visibility(DEFAULT_PROJECT_ID, "public")

    asyncio.run(expose_default_project())

    with TestClient(create_app(settings)) as client:
        me = client.get("/api/v1/auth/me")
        signup = client.post(
            "/api/v1/auth/signup",
            json={"email": "visitor@example.org", "password": "abc123"},
        )

    assert me.status_code == 200
    session = me.json()
    assert not session["signup_enabled"]
    assert "insight.execute" in session["permissions"][DEFAULT_PROJECT_ID]
    assert "insight.create" not in session["permissions"][DEFAULT_PROJECT_ID]
    assert signup.status_code == 404
    assert signup.json()["detail"] == "Public signup is disabled"


def test_first_run_setup_creates_and_signs_in_installation_admin(
    tmp_path: Path,
) -> None:
    settings = _secured_settings(tmp_path)

    with TestClient(create_app(settings)) as client:
        initial = client.get("/api/v1/auth/me")
        assert initial.status_code == 200
        assert initial.json()["auth_enabled"]
        assert initial.json()["setup_required"]
        assert initial.json()["password_policy"] == {
            "min_length": 6,
            "max_length": None,
            "require_uppercase": False,
            "require_lowercase": False,
            "require_number": False,
            "require_symbol": False,
        }

        created = client.post(
            "/api/v1/auth/setup",
            json={
                "display_name": "Installation Owner",
                "email": " OWNER@Example.org ",
                "password": "abc123",
            },
        )
        assert created.status_code == 201
        token = created.json()["access_token"]
        original_token = token
        profile = client.patch(
            "/api/v1/auth/me",
            json={
                "display_name": "Goodomics Owner",
                "email": "new-owner@example.org",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert profile.status_code == 200
        token = profile.json()["access_token"]
        assert (
            client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {original_token}"},
            ).status_code
            == 401
        )
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["principal"] == {
            "kind": "user",
            "user_id": me.json()["principal"]["user_id"],
            "email": "new-owner@example.org",
            "display_name": "Goodomics Owner",
            "is_admin": True,
            "must_change_password": False,
            "is_authenticated": True,
        }
        assert not me.json()["setup_required"]
        owner_id = me.json()["principal"]["user_id"]
        final_admin = client.patch(
            f"/api/v1/users/{owner_id}",
            json={"is_admin": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert final_admin.status_code == 400
        assert "at least one active administrator" in final_admin.json()["detail"]
        project = client.post(
            "/api/v1/projects",
            json={"name": "Admin project"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert project.status_code == 201
        project_id = project.json()["project_id"]
        created_user = client.post(
            "/api/v1/users",
            json={
                "email": "analyst@example.org",
                "password": "abc123",
                "display_name": "Analyst",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert created_user.status_code == 201
        updated_user = client.patch(
            f"/api/v1/users/{created_user.json()['user_id']}",
            json={
                "display_name": "Senior Analyst",
                "email": "ANALYST-UPDATED@example.org",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert updated_user.status_code == 200
        assert updated_user.json()["display_name"] == "Senior Analyst"
        assert updated_user.json()["email"] == "analyst-updated@example.org"
        roles = client.get(
            f"/api/v1/projects/{project_id}/roles",
            headers={"Authorization": f"Bearer {token}"},
        )
        viewer = next(role for role in roles.json() if role["name"] == "Viewer")
        membership = client.post(
            f"/api/v1/projects/{project_id}/members",
            json={
                "user_id": created_user.json()["user_id"],
                "role_id": viewer["role_id"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert membership.status_code == 201
        memberships = client.get(
            f"/api/v1/users/{created_user.json()['user_id']}/memberships",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert memberships.status_code == 200
        assert memberships.json()[0]["project_id"] == project_id
        assert memberships.json()[0]["role"]["name"] == "Viewer"
        assert "project.read" in memberships.json()[0]["role"]["permissions"]
        analyst = next(role for role in roles.json() if role["name"] == "Analyst")
        updated_membership = client.patch(
            f"/api/v1/projects/{project_id}/members/"
            f"{membership.json()['membership_id']}",
            json={"role_id": analyst["role_id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert updated_membership.status_code == 200
        assert updated_membership.json()["role"]["name"] == "Analyst"
        removed_membership = client.delete(
            f"/api/v1/projects/{project_id}/members/"
            f"{membership.json()['membership_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert removed_membership.status_code == 204
        memberships = client.get(
            f"/api/v1/users/{created_user.json()['user_id']}/memberships",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert memberships.json() == []
        assert (
            client.post(
                "/api/v1/auth/setup",
                json={
                    "email": "other@example.org",
                    "password": "abcdef",
                },
            ).status_code
            == 409
        )

    async def delete_all_users() -> None:
        async with (
            initialized_store(settings.database_url) as store,
            store.session() as session,
        ):
            await session.exec(delete(UserRecord))
            await session.commit()

    asyncio.run(delete_all_users())
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/v1/auth/setup")
        assert status.status_code == 200
        assert not status.json()["setup_required"]


def test_login_normalizes_email_and_private_projects_require_auth(
    tmp_path: Path,
) -> None:
    settings = _secured_settings(tmp_path)
    _create_user(settings, admin=True)

    with TestClient(create_app(settings)) as client:
        anonymous = client.get("/api/v1/projects")
        assert anonymous.status_code == 200
        assert anonymous.json() == []

        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": " admin@example.ORG ",
                "password": "correct horse battery staple",
            },
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/v1/projects", json={"name": "Private project"}, headers=headers
        )
        assert created.status_code == 201
        project_id = created.json()["project_id"]
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 401
        assert (
            client.get(f"/api/v1/projects/{project_id}", headers=headers).status_code
            == 200
        )


def test_missing_auth_secret_fails_fast() -> None:
    with pytest.raises(ValueError, match="GOODOMICS_AUTH_SECRET"):
        AuthSettings(enabled=True)


def test_toml_environment_and_cli_precedence_and_relative_paths(
    tmp_path: Path,
) -> None:
    config = tmp_path / "goodomics.toml"
    config.write_text(
        """
[database]
url = "sqlite+aiosqlite:///metadata.db"
[analytics]
root = "analytics"
[auth.password]
min_length = 9
require_number = true
[storage]
default_location = "local"
[storage.locations.local]
driver = "filesystem"
root = "managed"
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(
        config,
        environ={
            "GOODOMICS_ANALYTICS_ROOT": str(tmp_path / "environment"),
            "GOODOMICS_AUTH_PASSWORD_MIN_LENGTH": "7",
            "GOODOMICS_AUTH_PASSWORD_REQUIRE_SYMBOL": "true",
        },
        cli_overrides={"database": {"url": "sqlite+aiosqlite:///:memory:"}},
    )

    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.analytics_root == str(tmp_path / "environment")
    assert settings.file_root == str((tmp_path / "managed").resolve())
    assert settings.auth.password.min_length == 7
    assert settings.auth.password.require_number
    assert settings.auth.password.require_symbol


def test_first_run_config_uses_selected_path_and_never_overwrites(
    tmp_path: Path,
) -> None:
    config = tmp_path / "installation" / "settings.toml"
    environment = {"GOODOMICS_CONFIG": str(config)}

    selected, created = ensure_config_file(environ=environment)

    assert selected == config
    assert created
    packaged_example = (
        files("goodomics.server")
        .joinpath("goodomics.example.toml")
        .read_text(encoding="utf-8")
    )
    assert config.read_text(encoding="utf-8") == packaged_example
    repository_example = Path(__file__).parents[3] / "goodomics.example.toml"
    assert repository_example.read_text(encoding="utf-8") == packaged_example
    assert Settings.model_validate(tomllib.loads(packaged_example)) == Settings()
    settings = load_settings(environ=environment)
    assert settings.config_path == config
    expected_database = tmp_path / "installation" / ".goodomics" / "goodomics.db"
    assert settings.database_url == f"sqlite+aiosqlite:///{expected_database}"

    original = config.read_text(encoding="utf-8")
    selected_again, created_again = ensure_config_file(environ=environment)

    assert selected_again == config
    assert not created_again
    assert config.read_text(encoding="utf-8") == original


def test_filesystem_file_store_contract(tmp_path: Path) -> None:
    store = FilesystemFileStore(tmp_path / "files")

    metadata = store.upload("project/result.txt", io.BytesIO(b"result\n"))

    assert metadata.size_bytes == 7
    assert metadata.sha256 is not None
    assert store.metadata("project/result.txt").size_bytes == 7
    assert b"".join(store.iter_bytes("project/result.txt", chunk_size=2)) == b"result\n"
    store.delete("project/result.txt")
    with pytest.raises(FileNotFoundError):
        store.metadata("project/result.txt")
    with pytest.raises(ValueError):
        store.upload("../escape", io.BytesIO(b"no"))


def test_managed_project_file_upload_download_and_delete(tmp_path: Path) -> None:
    settings = Settings(
        database=DatabaseSettings(url=f"sqlite+aiosqlite:///{tmp_path / 'files.db'}"),
        storage=StorageSettings(
            locations={
                "default": StorageLocationSettings(
                    driver="filesystem", root=str(tmp_path / "managed")
                )
            }
        ),
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Files"}).json()
        uploaded = client.post(
            f"/api/v1/projects/{project['project_id']}/files",
            files={"upload": ("result.txt", b"result\n", "text/plain")},
        )
        assert uploaded.status_code == 201
        file = uploaded.json()
        assert file["storage_location"] == "default"
        assert file["object_key"].endswith("/result.txt")
        content = client.get(
            f"/api/v1/projects/{project['project_id']}/files/{file['file_id']}/content"
        )
        assert content.content == b"result\n"
        deleted = client.delete(
            f"/api/v1/projects/{project['project_id']}/files/{file['file_id']}"
        )
        assert deleted.status_code == 204
        assert (
            client.get(
                f"/api/v1/projects/{project['project_id']}/files/{file['file_id']}/content"
            ).status_code
            == 404
        )


class _StubS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_fileobj(self, source, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = source.read()

    def get_object(self, *, Bucket: str, Key: str):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str):
        return {
            "ContentLength": len(self.objects[(Bucket, Key)]),
            "ContentType": "application/octet-stream",
            "Metadata": {},
        }

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


def test_s3_file_store_contract_with_stub_client() -> None:
    client = _StubS3()
    store = S3FileStore(bucket="bucket", prefix="managed", client=client)

    uploaded = store.upload("project/result.txt", io.BytesIO(b"result"))

    assert uploaded.size_bytes == 6
    assert store.metadata("project/result.txt").size_bytes == 6
    assert b"".join(store.iter_bytes("project/result.txt")) == b"result"
    store.delete("project/result.txt")
    assert client.objects == {}
