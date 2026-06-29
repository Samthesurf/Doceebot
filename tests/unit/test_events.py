from datetime import UTC, datetime

from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.core.idempotency import inbound_event_key
from whatsapp_ai_agent.core.timestamps import local_date_and_time


def test_local_date_and_time_uses_lagos_timezone():
    local_date, local_time = local_date_and_time(
        datetime(2026, 1, 1, 23, 30, tzinfo=UTC),
        "Africa/Lagos",
    )
    assert str(local_date) == "2026-01-02"
    assert local_time.hour == 0
    assert local_time.minute == 30


def test_inbound_event_key_is_platform_scoped():
    received_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    event = InboundEvent(
        platform="telegram",
        platform_message_id="123:456",
        platform_user_id="123",
        platform_chat_id="123",
        message_type="text",
        text="Installed DB board",
        received_at=received_at,
        local_date=received_at.date(),
        local_time=received_at.time(),
        timezone="UTC",
    )
    assert inbound_event_key(event) == "telegram:123:456"
