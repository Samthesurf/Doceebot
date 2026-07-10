from datetime import UTC, datetime
from typing import Any

import pytest

from whatsapp_ai_agent.integrations.whatsapp_meta.parser import parse_meta_webhook_payload


def make_payload(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "9876543210987654",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "1234567890123456"},
                            "contacts": [{"wa_id": "2348012345678"}],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


def test_meta_parser_normalizes_text_message():
    events = parse_meta_webhook_payload(
        make_payload(
            {
                "from": "2348012345678",
                "id": "wamid.text-1",
                "timestamp": "1760097600",
                "type": "text",
                "text": {"body": "Installed the inverter changeover."},
            }
        ),
        received_at=datetime(2026, 10, 10, 12, 0, tzinfo=UTC),
    )

    assert len(events) == 1
    event = events[0]
    assert event.platform == "whatsapp_meta"
    assert event.platform_message_id == "wamid.text-1"
    assert event.platform_user_id == "2348012345678"
    assert event.platform_chat_id == "2348012345678"
    assert event.message_type == "text"
    assert event.text == "Installed the inverter changeover."
    assert event.platform_timestamp == datetime(2025, 10, 10, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("message", "expected_type", "expected_filename"),
    [
        (
            {
                "from": "2348012345678",
                "id": "wamid.image-1",
                "timestamp": "1760097600",
                "type": "image",
                "image": {
                    "id": "media-image-1",
                    "mime_type": "image/jpeg",
                    "caption": "Completed panel wiring",
                },
            },
            "image",
            None,
        ),
        (
            {
                "from": "2348012345678",
                "id": "wamid.voice-1",
                "timestamp": "1760097600",
                "type": "audio",
                "audio": {"id": "media-audio-1", "mime_type": "audio/ogg", "voice": True},
            },
            "voice",
            None,
        ),
        (
            {
                "from": "2348012345678",
                "id": "wamid.video-1",
                "timestamp": "1760097600",
                "type": "video",
                "video": {
                    "id": "media-video-1",
                    "mime_type": "video/mp4",
                    "caption": "Walkthrough clip",
                },
            },
            "video",
            None,
        ),
        (
            {
                "from": "2348012345678",
                "id": "wamid.document-1",
                "timestamp": "1760097600",
                "type": "document",
                "document": {
                    "id": "media-document-1",
                    "mime_type": "application/pdf",
                    "filename": "daily-report.pdf",
                    "caption": "Daily report",
                },
            },
            "document",
            "daily-report.pdf",
        ),
    ],
)
def test_meta_parser_normalizes_media_message(message, expected_type, expected_filename):
    event = parse_meta_webhook_payload(make_payload(message))[0]

    assert event.message_type == expected_type
    assert event.media[0].platform_media_id.startswith("media-")
    assert event.media[0].content_type
    assert event.media[0].filename == expected_filename
    if expected_type in {"image", "video", "document"}:
        assert event.text


def test_meta_parser_normalizes_location_message():
    event = parse_meta_webhook_payload(
        make_payload(
            {
                "from": "2348012345678",
                "id": "wamid.location-1",
                "timestamp": "1760097600",
                "type": "location",
                "location": {
                    "latitude": 6.5244,
                    "longitude": 3.3792,
                    "name": "Lagos Site Office",
                    "address": "Ikeja, Lagos",
                },
            }
        )
    )[0]

    assert event.message_type == "location"
    assert event.location is not None
    assert event.location.latitude == 6.5244
    assert event.location.longitude == 3.3792
    assert event.location.label == "Lagos Site Office"
    assert event.location.address == "Ikeja, Lagos"


def test_meta_parser_ignores_status_callbacks():
    payload = make_payload(
        {
            "from": "2348012345678",
            "id": "wamid.ignored",
            "timestamp": "1760097600",
            "type": "text",
            "text": {"body": "ignored"},
        }
    )
    value = payload["entry"][0]["changes"][0]["value"]
    value.pop("messages")
    value["statuses"] = [{"id": "wamid.outbound", "status": "delivered"}]

    assert parse_meta_webhook_payload(payload) == []


def test_meta_parser_rejects_message_without_sender():
    with pytest.raises(ValueError, match="from"):
        parse_meta_webhook_payload(
            make_payload(
                {
                    "id": "wamid.invalid",
                    "timestamp": "1760097600",
                    "type": "text",
                    "text": {"body": "Hello"},
                }
            )
        )
