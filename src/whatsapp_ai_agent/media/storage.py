from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote

from whatsapp_ai_agent.config import Settings, get_settings


@dataclass(frozen=True)
class StoredObject:
    backend: str
    key: str
    content_type: str | None = None
    size_bytes: int | None = None
    sha256_hex: str | None = None
    bucket: str | None = None
    local_path: Path | None = None
    etag: str | None = None
    url: str | None = None


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def normalize_object_key(key: str) -> str:
    """Normalize object keys while preventing path traversal."""

    parts = [part for part in key.replace("\\", "/").split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValueError("object key must not contain path traversal")
    return "/".join(parts)


def org_object_key(org_id: str, *parts: str) -> str:
    safe_parts = [normalize_object_key(part) for part in parts if part]
    return normalize_object_key("/".join(["orgs", org_id, *safe_parts]))


class LocalStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(self.settings.local_storage_dir)

    def path_for(self, *parts: str) -> Path:
        key = normalize_object_key("/".join(parts))
        path = self.root.joinpath(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        key = normalize_object_key(key)
        path = self.path_for(key)
        path.write_bytes(data)
        return StoredObject(
            backend="local",
            key=key,
            content_type=content_type,
            size_bytes=len(data),
            sha256_hex=sha256_bytes(data),
            local_path=path,
            url=self.public_url(key),
        )

    def save_file(
        self,
        key: str,
        path: Path,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        return self.save_bytes(
            key,
            path.read_bytes(),
            content_type=content_type,
            metadata=metadata,
        )

    def read_bytes(self, key: str) -> bytes:
        return self.path_for(key).read_bytes()

    def public_url(self, key: str) -> str | None:
        if not self.settings.public_media_base_url:
            return None
        base_url = self.settings.public_media_base_url.rstrip("/")
        return f"{base_url}/{quote(normalize_object_key(key))}"


class R2Storage:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        s3_client: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.cloudflare_r2_bucket:
            raise RuntimeError("CLOUDFLARE_R2_BUCKET is not configured")
        self.bucket = self.settings.cloudflare_r2_bucket
        self._s3_client = s3_client

    @property
    def s3_client(self) -> Any:
        if self._s3_client is None:
            self._s3_client = self._build_s3_client()
        return self._s3_client

    def _build_s3_client(self) -> Any:
        if not self.settings.r2_endpoint_url:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_R2_ENDPOINT_URL is required")
        if not self.settings.cloudflare_r2_access_key_id:
            raise RuntimeError("CLOUDFLARE_R2_ACCESS_KEY_ID is required for R2 object uploads")
        if not self.settings.cloudflare_r2_secret_access_key:
            raise RuntimeError("CLOUDFLARE_R2_SECRET_ACCESS_KEY is required for R2 object uploads")
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - exercised only in incomplete installs
            raise RuntimeError("boto3 is required for R2 object uploads") from exc

        return boto3.client(
            service_name="s3",
            endpoint_url=self.settings.r2_endpoint_url,
            aws_access_key_id=self.settings.cloudflare_r2_access_key_id,
            aws_secret_access_key=self.settings.cloudflare_r2_secret_access_key,
            region_name="auto",
        )

    def save_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        key = normalize_object_key(key)
        put_kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "Metadata": self._clean_metadata(metadata or {}),
        }
        if content_type:
            put_kwargs["ContentType"] = content_type
        response = self.s3_client.put_object(**put_kwargs)
        etag = response.get("ETag") if isinstance(response, dict) else None
        return StoredObject(
            backend="r2",
            bucket=self.bucket,
            key=key,
            content_type=content_type,
            size_bytes=len(data),
            sha256_hex=sha256_bytes(data),
            etag=etag.strip('"') if isinstance(etag, str) else None,
            url=self.public_url(key),
        )

    def save_file(
        self,
        key: str,
        path: Path,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        return self.save_bytes(
            key,
            path.read_bytes(),
            content_type=content_type,
            metadata=metadata,
        )

    def presigned_get_url(self, key: str, *, expires_seconds: int = 3600) -> str:
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": normalize_object_key(key)},
            ExpiresIn=expires_seconds,
        )

    def read_bytes(self, key: str) -> bytes:
        response = self.s3_client.get_object(Bucket=self.bucket, Key=normalize_object_key(key))
        body = response["Body"]
        return body.read()

    def public_url(self, key: str) -> str | None:
        if not self.settings.cloudflare_r2_public_base_url:
            return None
        base_url = self.settings.cloudflare_r2_public_base_url.rstrip("/")
        return f"{base_url}/{quote(normalize_object_key(key))}"

    @staticmethod
    def _clean_metadata(metadata: dict[str, str]) -> dict[str, str]:
        clean: dict[str, str] = {}
        for key, value in metadata.items():
            if value is None:
                continue
            clean[key.lower().replace("_", "-")] = str(value)[:500]
        return clean


def get_media_storage(settings: Settings | None = None) -> LocalStorage | R2Storage:
    settings = settings or get_settings()
    if settings.media_storage_backend == "r2":
        return R2Storage(settings)
    return LocalStorage(settings)
