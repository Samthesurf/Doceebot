import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.media.storage import (
    LocalStorage,
    R2Storage,
    normalize_object_key,
    org_object_key,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.put_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        return {"ETag": '"etag-123"'}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://r2.example/{operation}/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"


def test_normalize_object_key_blocks_path_traversal():
    assert normalize_object_key("orgs/abc//file.txt") == "orgs/abc/file.txt"
    with pytest.raises(ValueError):
        normalize_object_key("orgs/abc/../secrets.txt")


def test_org_object_key_is_always_under_org_prefix():
    assert org_object_key("org-1", "reports", "daily.docx") == "orgs/org-1/reports/daily.docx"


def test_local_storage_saves_hash_and_optional_public_url(tmp_path):
    settings = Settings(
        local_storage_dir=str(tmp_path),
        public_media_base_url="https://media.example/files",
        _env_file=None,
    )
    storage = LocalStorage(settings)

    stored = storage.save_bytes("orgs/org-1/report.txt", b"hello", content_type="text/plain")

    assert stored.backend == "local"
    assert stored.key == "orgs/org-1/report.txt"
    assert stored.local_path is not None
    assert stored.local_path.read_bytes() == b"hello"
    assert stored.size_bytes == 5
    assert stored.sha256_hex == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert stored.url == "https://media.example/files/orgs/org-1/report.txt"


def test_r2_storage_uploads_with_metadata_hash_and_public_url():
    fake_s3 = FakeS3Client()
    settings = Settings(
        cloudflare_account_id="account-1",
        cloudflare_r2_bucket="doceebot-storage",
        cloudflare_r2_public_base_url="https://pub.example",
        _env_file=None,
    )
    storage = R2Storage(settings, s3_client=fake_s3)

    stored = storage.save_bytes(
        "orgs/org-1/rag/manual.txt",
        b"manual",
        content_type="text/plain",
        metadata={"org_id": "org-1", "source_type": "company_document"},
    )

    assert stored.backend == "r2"
    assert stored.bucket == "doceebot-storage"
    assert stored.etag == "etag-123"
    assert stored.url == "https://pub.example/orgs/org-1/rag/manual.txt"
    put_call = fake_s3.put_calls[0]
    assert put_call["Bucket"] == "doceebot-storage"
    assert put_call["Key"] == "orgs/org-1/rag/manual.txt"
    assert put_call["Body"] == b"manual"
    assert put_call["ContentType"] == "text/plain"
    assert put_call["Metadata"] == {"org-id": "org-1", "source-type": "company_document"}


def test_r2_storage_can_generate_presigned_url():
    settings = Settings(
        cloudflare_account_id="account-1",
        cloudflare_r2_bucket="doceebot-storage",
        _env_file=None,
    )
    storage = R2Storage(settings, s3_client=FakeS3Client())

    assert storage.presigned_get_url("orgs/org-1/report.docx", expires_seconds=600) == (
        "https://r2.example/get_object/doceebot-storage/orgs/org-1/report.docx?exp=600"
    )
