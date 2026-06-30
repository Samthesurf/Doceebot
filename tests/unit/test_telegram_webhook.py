from datetime import UTC, datetime

import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.integrations.telegram import webhook


def make_event(**overrides: object) -> InboundEvent:
    values = {
        "platform": "telegram",
        "platform_message_id": "1001:42",
        "platform_user_id": "2002",
        "platform_chat_id": "1001",
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


def test_build_acknowledgement_for_text_message():
    assert webhook.build_acknowledgement(make_event()) == (
        "Received your work update. I have parsed it and the AI logging step is next."
    )


@pytest.mark.asyncio
async def test_acknowledge_telegram_event_sends_text(monkeypatch):
    sent_messages = []

    class FakeSender:
        def __init__(self, *, settings):
            self.settings = settings

        async def send_text(self, *, chat_id, text):
            sent_messages.append({"chat_id": chat_id, "text": text})

    monkeypatch.setattr(webhook, "TelegramSender", FakeSender)

    settings = Settings(telegram_bot_token="token", _env_file=None)
    await webhook.acknowledge_telegram_event(make_event(), settings)

    assert sent_messages == [
        {
            "chat_id": "1001",
            "text": "Received your work update. I have parsed it and the AI logging step is next.",
        }
    ]
