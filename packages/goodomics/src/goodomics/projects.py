from __future__ import annotations

import re
import secrets
import string
from pathlib import Path

DEFAULT_PROJECT_ID = "prj_default"
DEFAULT_PROJECT_SLUG = "default"
DEFAULT_PROJECT_NAME = "Default Project"

PROJECT_ID_RE = re.compile(r"^prj_[a-z]{20}$")
PROJECT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def new_project_id() -> str:
    alphabet = string.ascii_lowercase
    return "prj_" + "".join(secrets.choice(alphabet) for _ in range(20))


def is_project_id(value: str) -> bool:
    return value == DEFAULT_PROJECT_ID or PROJECT_ID_RE.fullmatch(value) is not None


def slugify_project(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        slug = DEFAULT_PROJECT_SLUG
    return slug[:63].strip("-") or DEFAULT_PROJECT_SLUG


def validate_project_slug(value: str) -> str:
    slug = slugify_project(value)
    if PROJECT_SLUG_RE.fullmatch(slug) is None:
        raise ValueError(
            "Project slug must contain lowercase letters, numbers, or hyphens"
        )
    return slug


def display_name_from_slug(slug: str) -> str:
    return (
        " ".join(part.capitalize() for part in slug.split("-") if part)
        or DEFAULT_PROJECT_NAME
    )


def analytics_path_for_project(root: Path | str, project_id: str) -> Path:
    return Path(root) / "projects" / project_id / "analytics.duckdb"
