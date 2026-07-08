from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.integrations.whatsapp_twilio import webhook


class FakeRequest:
    def __init__(self, form: dict[str, str]) -> None:
        self._form = form
        self.headers = {}
        self.url = SimpleNamespace(path="/webhooks/twilio/whatsapp")
        self.app = SimpleNamespace(state=SimpleNamespace())

    async def form(self) -> dict[str, str]:
        return self._form


def make_twilio_event(**overrides: object) -> InboundEvent:
    values = {
        "platform": "whatsapp_twilio",
        "platform_message_id": "SM123",
        "platform_user_id": "2348012345678",
        "platform_chat_id": "whatsapp:+2348012345678",
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


@pytest.mark.asyncio
async def test_receive_twilio_media_returns_ack_and_defers_processing(monkeypatch):
    processed: list[dict[str, object]] = []
    sent_replies: list[dict[str, str]] = []

    async def fake_process_live_twilio_event(event, *, settings, db_session):
        processed.append({"sid": event.platform_message_id, "db_session": db_session})
        return "Final processed voice reply"

    async def fake_send_twilio_text_reply(event, body, *, settings):
        sent_replies.append({"to": event.platform_chat_id, "body": body})

    class FakeSession:
        def __enter__(self):
            return "background-db-session"

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeSessionFactory:
        def __call__(self):
            return FakeSession()

    monkeypatch.setattr(webhook, "process_live_twilio_event", fake_process_live_twilio_event)
    monkeypatch.setattr(webhook, "send_twilio_text_reply", fake_send_twilio_text_reply)
    monkeypatch.setattr(webhook, "get_session_factory", lambda settings=None: FakeSessionFactory())

    background_tasks = BackgroundTasks()
    response = await webhook.receive_twilio_whatsapp(
        FakeRequest(
            {
                "MessageSid": "MMVOICE123",
                "From": "whatsapp:+2348012345678",
                "To": "whatsapp:+14155238886",
                "WaId": "2348012345678",
                "Body": "",
                "NumMedia": "1",
                "MediaUrl0": "https://api.twilio.com/media/ME123",
                "MediaContentType0": "audio/ogg",
            }
        ),
        background_tasks,
        settings=Settings(app_env="development", twilio_webhook_auth_enabled=False, _env_file=None),
        db_session="request-db-session",
    )

    assert response.media_type == "application/xml"
    assert b"I received your voice upload" in response.body
    assert b"Final processed voice reply" not in response.body
    assert processed == []

    await background_tasks()

    assert processed == [{"sid": "MMVOICE123", "db_session": "background-db-session"}]
    assert sent_replies == [
        {
            "to": "whatsapp:+2348012345678",
            "body": "Final processed voice reply",
        }
    ]


@pytest.mark.asyncio
async def test_receive_twilio_text_acks_fast_and_defers_reply(monkeypatch):
    processed: list[str] = []
    sent_replies: list[dict[str, str]] = []

    async def fake_process_live_twilio_event(event, *, settings, db_session):
        processed.append(db_session)
        return "Final text reply"

    async def fake_send_twilio_text_reply(event, body, *, settings):
        sent_replies.append({"to": event.platform_chat_id, "body": body})

    monkeypatch.setattr(webhook, "process_live_twilio_event", fake_process_live_twilio_event)
    monkeypatch.setattr(webhook, "send_twilio_text_reply", fake_send_twilio_text_reply)

    class FakeSession:
        def __enter__(self):
            return "background-db-session"

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeSessionFactory:
        def __call__(self):
            return FakeSession()

    monkeypatch.setattr(webhook, "get_session_factory", lambda settings=None: FakeSessionFactory())

    background_tasks = BackgroundTasks()
    response = await webhook.receive_twilio_whatsapp(
        FakeRequest(
            {
                "MessageSid": "SMTEXT123",
                "From": "whatsapp:+234****5678",
                "To": "whatsapp:+141****8886",
                "WaId": "2348012345678",
                "Body": "Completed DB dressing",
                "NumMedia": "0",
            }
        ),
        background_tasks,
        settings=Settings(app_env="development", twilio_webhook_auth_enabled=False, _env_file=None),
        db_session="request-db-session",
    )

    # The webhook returns a fast TwiML acknowledgement, not the final reply.
    assert b"Final text reply" not in response.body
    assert b"I received your work update" in response.body
    assert processed == []  # heavy work is deferred, not run in the request

    # Draining the background task runs the AI turn and sends both the interim
    # "thinking" message and the final reply as follow-ups.
    await background_tasks()
    assert processed == ["background-db-session"]
    bodies = [r["body"] for r in sent_replies]
    assert webhook._INTERIM_THINKING_MESSAGE in bodies
    assert "Final text reply" in bodies


@pytest.mark.asyncio
async def test_send_twilio_text_reply_uses_configured_whatsapp_sender(monkeypatch):
    calls: list[dict[str, str]] = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(sid="SMOUT")

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(webhook, "build_twilio_client", lambda settings: FakeClient())

    await webhook.send_twilio_text_reply(
        make_twilio_event(),
        "Done processing",
        settings=Settings(
            twilio_account_sid="AC123",
            twilio_auth_token="auth-token",
            twilio_whatsapp_from="whatsapp:+14155238886",
            _env_file=None,
        ),
    )

    assert calls == [
        {
            "to": "whatsapp:+2348012345678",
            "body": "Done processing",
            "from_": "whatsapp:+14155238886",
        }
    ]
