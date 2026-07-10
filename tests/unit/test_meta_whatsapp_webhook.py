import asyncio
import hmac
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.models import Base, InboundEventClaim
from whatsapp_ai_agent.integrations.whatsapp_meta import webhook
from whatsapp_ai_agent.main import create_app


class FakeRequest:
    def __init__(self, body: bytes, *, signature: str | None = None) -> None:
        self._body = body
        self.headers = {"X-Hub-Signature-256": signature} if signature else {}
        self.app = SimpleNamespace(state=SimpleNamespace())

    async def body(self) -> bytes:
        return self._body


def make_event(**overrides: object) -> InboundEvent:
    values = {
        "platform": "whatsapp_meta",
        "platform_message_id": "wamid.inbound-1",
        "platform_user_id": "2348012345678",
        "platform_chat_id": "2348012345678",
        "message_type": "text",
        "text": "Completed DB dressing",
        "received_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        "local_date": "2026-01-01",
        "local_time": "13:00:00",
        "timezone": "Africa/Lagos",
        "raw_payload": {},
    }
    values.update(overrides)
    return InboundEvent(**values)


def meta_settings() -> Settings:
    return Settings(
        meta_whatsapp_enabled=True,
        meta_webhook_auth_enabled=True,
        meta_app_secret="meta-app-secret",
        meta_webhook_verify_token="meta-verify-token",
        meta_access_token="meta-access-token",
        meta_phone_number_id="1234567890123456",
        _env_file=None,
    )


def signed_request(payload: dict[str, object], settings: Settings) -> FakeRequest:
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    assert settings.meta_app_secret is not None
    signature = "sha256=" + hmac.new(
        settings.meta_app_secret.encode(), raw_body, "sha256"
    ).hexdigest()
    return FakeRequest(raw_body, signature=signature)


def test_meta_webhook_router_is_registered_on_the_application():
    settings = meta_settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    response = TestClient(app).get(
        "/webhooks/meta/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "meta-verify-token",
            "hub.challenge": "challenge-value",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge-value"


def test_meta_event_claim_is_unique_across_database_sessions(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(webhook, "get_session_factory", lambda settings: factory)

    assert webhook.claim_meta_event(make_event(), settings=meta_settings())
    assert not webhook.claim_meta_event(make_event(), settings=meta_settings())


@pytest.mark.asyncio
async def test_deferred_meta_processing_releases_claim_after_success(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    event = make_event()
    with factory() as db_session:
        db_session.add(
            InboundEventClaim(
                platform=event.platform,
                platform_message_id=event.platform_message_id,
            )
        )
        db_session.commit()

    async def fake_process_live(event, *, settings, db_session):
        return "Saved your update."

    class FakeSender:
        def __init__(self, *, settings):
            self.settings = settings

        async def send_text(self, *, to, body):
            return "wamid.outbound"

    monkeypatch.setattr(webhook, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(webhook, "process_live_meta_event", fake_process_live)
    monkeypatch.setattr(webhook, "MetaWhatsAppSender", FakeSender)

    await webhook.process_deferred_meta_event(event, settings=meta_settings())

    with factory() as db_session:
        assert list(db_session.scalars(select(InboundEventClaim))) == []


@pytest.mark.asyncio
async def test_deferred_meta_processing_releases_claim_after_failure(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    event = make_event()
    with factory() as db_session:
        db_session.add(
            InboundEventClaim(
                platform=event.platform,
                platform_message_id=event.platform_message_id,
            )
        )
        db_session.commit()

    async def failing_process_live(event, *, settings, db_session):
        raise RuntimeError("temporary processing failure")

    class FakeSender:
        def __init__(self, *, settings):
            self.settings = settings

        async def send_text(self, *, to, body):
            return "wamid.error"

    monkeypatch.setattr(webhook, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(webhook, "process_live_meta_event", failing_process_live)
    monkeypatch.setattr(webhook, "MetaWhatsAppSender", FakeSender)

    await webhook.process_deferred_meta_event(event, settings=meta_settings())

    with factory() as db_session:
        assert list(db_session.scalars(select(InboundEventClaim))) == []


@pytest.mark.asyncio
async def test_meta_webhook_verification_returns_raw_challenge():
    response = await webhook.verify_meta_whatsapp_webhook(
        hub_mode="subscribe",
        hub_verify_token="meta-verify-token",
        hub_challenge="challenge-value",
        settings=meta_settings(),
    )

    assert response.status_code == 200
    assert response.body == b"challenge-value"
    assert response.media_type == "text/plain"


@pytest.mark.asyncio
async def test_meta_webhook_verification_rejects_wrong_token():
    with pytest.raises(HTTPException) as exc_info:
        await webhook.verify_meta_whatsapp_webhook(
            hub_mode="subscribe",
            hub_verify_token="wrong-token",
            hub_challenge="challenge-value",
            settings=meta_settings(),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_meta_webhook_rejects_invalid_signature():
    request = FakeRequest(b'{"object":"whatsapp_business_account"}', signature="sha256=bad")

    with pytest.raises(HTTPException) as exc_info:
        await webhook.receive_meta_whatsapp(request, settings=meta_settings())

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_meta_webhook_returns_503_when_claim_storage_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        webhook,
        "parse_meta_webhook_payload",
        lambda payload, timezone_name: [make_event()],
    )

    def unavailable_claim(event, *, settings):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(webhook, "claim_meta_event", unavailable_claim)
    settings = meta_settings()
    request = signed_request({"object": "whatsapp_business_account", "entry": []}, settings)

    with pytest.raises(HTTPException) as exc_info:
        await webhook.receive_meta_whatsapp(request, settings=settings)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_meta_webhook_acks_fast_and_defers_each_inbound_message(monkeypatch):
    processed: list[InboundEvent] = []

    async def fake_process_deferred(event, *, settings):
        processed.append(event)

    monkeypatch.setattr(
        webhook,
        "parse_meta_webhook_payload",
        lambda payload, timezone_name: [make_event()],
    )
    monkeypatch.setattr(webhook, "process_deferred_meta_event", fake_process_deferred)
    monkeypatch.setattr(webhook, "claim_meta_event", lambda event, settings: True)
    settings = meta_settings()
    request = signed_request({"object": "whatsapp_business_account", "entry": []}, settings)

    response = await webhook.receive_meta_whatsapp(request, settings=settings)

    for _ in range(100):
        if processed:
            break
        await asyncio.sleep(0.02)

    assert response == {"status": "accepted"}
    assert processed == [make_event()]
    assert request.app.state.last_meta_event == make_event()


@pytest.mark.asyncio
async def test_meta_webhook_does_not_dispatch_an_event_with_an_existing_claim(monkeypatch):
    dispatched: list[InboundEvent] = []
    monkeypatch.setattr(
        webhook,
        "parse_meta_webhook_payload",
        lambda payload, timezone_name: [make_event()],
    )
    monkeypatch.setattr(webhook, "claim_meta_event", lambda event, settings: False)
    monkeypatch.setattr(
        webhook,
        "dispatch_meta_event",
        lambda event, settings: dispatched.append(event),
    )
    settings = meta_settings()
    request = signed_request({"object": "whatsapp_business_account", "entry": []}, settings)

    response = await webhook.receive_meta_whatsapp(request, settings=settings)

    assert response == {"status": "accepted"}
    assert dispatched == []


@pytest.mark.asyncio
async def test_meta_status_callback_is_accepted_without_deferred_work(monkeypatch):
    dispatched: list[InboundEvent] = []
    monkeypatch.setattr(
        webhook,
        "parse_meta_webhook_payload",
        lambda payload, timezone_name: [],
    )
    monkeypatch.setattr(
        webhook,
        "dispatch_meta_event",
        lambda event, settings: dispatched.append(event),
    )
    settings = meta_settings()
    request = signed_request({"object": "whatsapp_business_account", "entry": []}, settings)

    response = await webhook.receive_meta_whatsapp(request, settings=settings)

    assert response == {"status": "accepted"}
    assert dispatched == []
