"""Named managed-file storage adapters for filesystems and S3-compatible APIs."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Protocol, cast


@dataclass(frozen=True)
class FileMetadata:
    size_bytes: int
    sha256: str | None = None
    content_type: str | None = None


class FileStore(Protocol):
    """Contract for one authoritative managed file location."""

    def upload(self, object_key: str, source: BinaryIO) -> FileMetadata: ...

    def open(self, object_key: str) -> BinaryIO: ...

    def iter_bytes(
        self, object_key: str, chunk_size: int = 1024 * 1024
    ) -> Iterator[bytes]: ...

    def metadata(self, object_key: str) -> FileMetadata: ...

    def delete(self, object_key: str) -> None: ...


class FilesystemFileStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def upload(self, object_key: str, source: BinaryIO) -> FileMetadata:
        target = self._path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with target.open("wb") as destination:
            while chunk := source.read(1024 * 1024):
                destination.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        return FileMetadata(size_bytes=size, sha256=digest.hexdigest())

    def open(self, object_key: str) -> BinaryIO:
        return self._path(object_key).open("rb")

    def iter_bytes(
        self, object_key: str, chunk_size: int = 1024 * 1024
    ) -> Iterator[bytes]:
        with self.open(object_key) as handle:
            while chunk := handle.read(chunk_size):
                yield chunk

    def metadata(self, object_key: str) -> FileMetadata:
        path = self._path(object_key)
        if not path.is_file():
            raise FileNotFoundError(object_key)
        return FileMetadata(size_bytes=path.stat().st_size)

    def delete(self, object_key: str) -> None:
        self._path(object_key).unlink(missing_ok=True)

    def _path(self, object_key: str) -> Path:
        key = _validated_key(object_key)
        path = (self.root / key).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Object key escapes the storage root") from exc
        return path


class S3FileStore:
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        region: str | None = None,
        client: object | None = None,
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def upload(self, object_key: str, source: BinaryIO) -> FileMetadata:
        digest = hashlib.sha256()
        # Spooled input keeps the adapter compatible with boto3's standard
        # credential chain and upload_fileobj API while calculating a checksum.
        from tempfile import SpooledTemporaryFile

        with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as buffered:
            size = 0
            while chunk := source.read(1024 * 1024):
                buffered.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            buffered.seek(0)
            cast(object, self.client).upload_fileobj(  # type: ignore[attr-defined]
                buffered, self.bucket, self._key(object_key)
            )
        return FileMetadata(size_bytes=size, sha256=digest.hexdigest())

    def open(self, object_key: str) -> BinaryIO:
        response = cast(object, self.client).get_object(  # type: ignore[attr-defined]
            Bucket=self.bucket, Key=self._key(object_key)
        )
        return cast(BinaryIO, response["Body"])

    def iter_bytes(
        self, object_key: str, chunk_size: int = 1024 * 1024
    ) -> Iterator[bytes]:
        body = self.open(object_key)
        try:
            while chunk := body.read(chunk_size):
                yield chunk
        finally:
            body.close()

    def metadata(self, object_key: str) -> FileMetadata:
        try:
            response = cast(object, self.client).head_object(  # type: ignore[attr-defined]
                Bucket=self.bucket, Key=self._key(object_key)
            )
        except Exception as exc:
            if _is_s3_missing(exc):
                raise FileNotFoundError(object_key) from exc
            raise
        metadata = response.get("Metadata", {})
        return FileMetadata(
            size_bytes=int(response["ContentLength"]),
            sha256=metadata.get("sha256"),
            content_type=response.get("ContentType"),
        )

    def delete(self, object_key: str) -> None:
        cast(object, self.client).delete_object(  # type: ignore[attr-defined]
            Bucket=self.bucket, Key=self._key(object_key)
        )

    def _key(self, object_key: str) -> str:
        key = _validated_key(object_key)
        return f"{self.prefix}/{key}" if self.prefix else key


class FileStoreRegistry:
    def __init__(self, stores: Mapping[str, FileStore], default_location: str) -> None:
        if default_location not in stores:
            raise ValueError(f"Unknown default storage location: {default_location}")
        self._stores = dict(stores)
        self.default_location = default_location

    def get(self, name: str | None = None) -> FileStore:
        location = name or self.default_location
        try:
            return self._stores[location]
        except KeyError as exc:
            raise ValueError(f"Unknown storage location: {location}") from exc

    @property
    def locations(self) -> tuple[str, ...]:
        return tuple(sorted(self._stores))

    @classmethod
    def from_settings(cls, settings: Any) -> FileStoreRegistry:
        stores = {
            name: _store_from_location(location)
            for name, location in settings.storage.locations.items()
        }
        return cls(stores, settings.storage.default_location)


def _store_from_location(location: Any) -> FileStore:
    if location.driver == "filesystem":
        return FilesystemFileStore(cast(str, location.root))
    return S3FileStore(
        bucket=cast(str, location.bucket),
        prefix=location.prefix,
        endpoint_url=location.endpoint_url,
        region=location.region,
    )


def _validated_key(object_key: str) -> str:
    key = PurePosixPath(object_key.strip().lstrip("/"))
    if not object_key.strip() or ".." in key.parts:
        raise ValueError("Invalid object key")
    return str(key)


def _is_s3_missing(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    code = response.get("Error", {}).get("Code")
    return str(code) in {"404", "NoSuchKey", "NotFound"}
