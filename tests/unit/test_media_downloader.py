from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.events import InboundEvent, MediaRef
from whatsapp_ai_agent.db.models import Base, ManagedDocument, Membership, Organization, User
from whatsapp_ai_agent.integrations.telegram import webhook as telegram_webhook
from whatsapp_ai_agent.llm.schemas import ChatParseResult, WorkLogDraft
from whatsapp_ai_agent.media.downloader import (
    DownloadedMedia,
    TelegramMediaDownloader,
    TwilioMediaDownloader,
    download_and_store_event_media,
)
from whatsapp_ai_agent.workflows.chat_processing import process_inbound_event


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as session:
        yield session


def make_event(**overrides: object) -> InboundEvent:
    values = {
        "platform": "telegram",
        "platform_message_id": "1001:42",
        "platform_user_id": "2002",
        "platform_chat_id": "1001",
        "message_type": "document",
        "text": "Please log this attached note.",
        "media": [
            MediaRef(
                platform_media_id="file-1",
                filename="site-note.txt",
                content_type="text/plain",
                index=0,
            )
        ],
        "received_at": datetime(2026, 7, 2, 12, 0, tzinfo=UTC),
        "local_date": "2026-07-02",
        "local_time": "13:00:00",
        "timezone": "Africa/Lagos",
        "raw_payload": {},
    }
    values.update(overrides)
    return InboundEvent(**values)


@pytest.mark.asyncio
async def test_telegram_file_id_downloads_and_stores_actual_bytes(tmp_path):
    org_id = uuid4()
    event = make_event(org_id=org_id)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getFile"):
            return httpx.Response(
                200,
                json={"ok": True, "result": {"file_path": "documents/site-note.txt"}},
            )
        assert request.url.path.endswith("/documents/site-note.txt")
        return httpx.Response(
            200,
            content=b"site note bytes",
            headers={"content-type": "text/plain"},
        )

    settings = Settings(
        telegram_bot_token="telegram-token",
        local_storage_dir=str(tmp_path),
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        downloader = TelegramMediaDownloader(settings, http_client=http_client)
        stored_event, stored_items = await download_and_store_event_media(
            event,
            settings=settings,
            downloader=downloader,
        )

    assert stored_items[0].data == b"site note bytes"
    stored_media = stored_event.media[0]
    assert stored_media.storage_backend == "local"
    assert stored_media.storage_key.startswith(f"orgs/{org_id}/media/telegram/2026-07-02/")
    assert stored_media.size_bytes == len(b"site note bytes")
    assert stored_media.sha256_hex
    assert stored_items[0].stored.local_path is not None
    assert stored_items[0].stored.local_path.read_bytes() == b"site note bytes"


@pytest.mark.asyncio
async def test_twilio_media_url_downloads_with_auth_and_stores_bytes(tmp_path):
    org_id = uuid4()
    event = make_event(
        org_id=org_id,
        platform="whatsapp_twilio",
        platform_message_id="SM123",
        platform_user_id="2348012345678",
        platform_chat_id="whatsapp:+2348012345678",
        media=[
            MediaRef(
                url="https://api.twilio.com/2010-04-01/Accounts/AC123/Messages/SM123/Media/ME123",
                content_type="image/jpeg",
                index=0,
            )
        ],
        message_type="image",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization", "").startswith("Basic ")
        return httpx.Response(200, content=b"jpeg-bytes", headers={"content-type": "image/jpeg"})

    settings = Settings(
        twilio_account_sid="AC123",
        twilio_auth_token="auth-token",
        local_storage_dir=str(tmp_path),
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        downloader = TwilioMediaDownloader(settings, http_client=http_client)
        stored_event, stored_items = await download_and_store_event_media(
            event,
            settings=settings,
            downloader=downloader,
        )

    assert stored_items[0].data == b"jpeg-bytes"
    stored_media = stored_event.media[0]
    assert stored_media.filename == "ME123"
    assert stored_media.storage_key.startswith(f"orgs/{org_id}/media/whatsapp_twilio/2026-07-02/")
    assert stored_items[0].stored.local_path is not None
    assert stored_items[0].stored.local_path.read_bytes() == b"jpeg-bytes"


class FakeDownloader:
    async def download(self, media: MediaRef) -> DownloadedMedia:
        return DownloadedMedia(
            media=media,
            data=b"stored document bytes",
            content_type="text/plain",
            filename="site-note.txt",
        )


class FakeNormalizer:
    async def parse_chat_event(self, event, *, media_extractions=None):
        assert event.media[0].storage_key
        return ChatParseResult(
            intent="work_log",
            work_logs=[
                WorkLogDraft(
                    work_date=event.local_date,
                    timezone=event.timezone,
                    title="Stored upload test",
                    description="Stored upload test",
                    actions_taken=["Verified stored media metadata"],
                    confidence=0.9,
                )
            ],
            summary_for_user="Stored upload test",
            follow_up_questions=[],
            confidence=0.9,
        )


@pytest.mark.asyncio
async def test_process_inbound_event_downloads_media_and_registers_available_document(
    tmp_path,
    db_session,
):
    org_id = uuid4()
    user_id = uuid4()
    settings = Settings(local_storage_dir=str(tmp_path), _env_file=None)

    result = await process_inbound_event(
        make_event(),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=FakeNormalizer(),
        settings=settings,
        download_media=True,
        media_downloader=FakeDownloader(),
        store_reports=False,
    )

    document = db_session.scalar(select(ManagedDocument).where(ManagedDocument.org_id == org_id))
    assert document is not None
    assert document.status == "available"
    assert document.storage_backend == "local"
    assert document.sha256_hex == result.stored_media[0].media.sha256_hex
    assert result.stored_media[0].stored.local_path is not None
    assert result.stored_media[0].stored.local_path.read_bytes() == b"stored document bytes"
    assert "Stored site-note.txt as an editable TEXT document." in result.reply_text


@dataclass(frozen=True)
class FakeProcessingResult:
    reply_text: str
    document_results: list = field(default_factory=list)


@pytest.mark.asyncio
async def test_live_telegram_processing_resolves_tenant_and_requests_media_download(
    monkeypatch,
    db_session,
):
    org = Organization(name="Tenant A")
    user = User(display_name="Worker", telegram_user_id="2002")
    db_session.add_all([org, user])
    db_session.flush()
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="worker"))
    db_session.flush()

    captured = {}

    async def fake_process(event, **kwargs):
        captured["event"] = event
        captured["kwargs"] = kwargs
        return FakeProcessingResult(reply_text="processed")

    monkeypatch.setattr(telegram_webhook, "process_inbound_event", fake_process)

    reply = await telegram_webhook.process_live_telegram_event(
        make_event(),
        settings=Settings(local_storage_dir="storage", _env_file=None),
        db_session=db_session,
    )

    assert reply == "processed"
    assert captured["event"].org_id == org.id
    assert captured["event"].user_id == user.id
    assert captured["kwargs"]["download_media"] is True
    assert captured["kwargs"]["extract_media"] is False
    assert captured["kwargs"]["db_session"] is db_session
