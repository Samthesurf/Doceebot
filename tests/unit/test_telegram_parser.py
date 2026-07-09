from datetime import UTC, datetime

from whatsapp_ai_agent.integrations.telegram.parser import parse_telegram_update


def test_telegram_parser_handles_text_message():
    event = parse_telegram_update(
        {
            "update_id": 1,
            "message": {
                "message_id": 42,
                "date": 1767225600,
                "chat": {"id": 1001},
                "from": {"id": 2002},
                "text": "Completed DB dressing",
            },
        },
        received_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    assert event.platform == "telegram"
    assert event.platform_message_id == "1001:42"
    assert event.message_type == "text"
    assert event.text == "Completed DB dressing"


def test_telegram_parser_handles_voice_message():
    event = parse_telegram_update(
        {
            "message": {
                "message_id": 43,
                "chat": {"id": 1001},
                "from": {"id": 2002},
                "voice": {"file_id": "voice-file", "mime_type": "audio/ogg", "file_size": 1234},
            }
        }
    )
    assert event.message_type == "voice"
    assert event.media[0].platform_media_id == "voice-file"


def test_telegram_parser_handles_video_message():
    event = parse_telegram_update(
        {
            "message": {
                "message_id": 44,
                "chat": {"id": 1001},
                "from": {"id": 2002},
                "caption": "Short site walkthrough",
                "video": {
                    "file_id": "video-file",
                    "mime_type": "video/mp4",
                    "file_size": 4321,
                    "file_name": "walkthrough.mp4",
                },
            }
        }
    )
    assert event.message_type == "video"
    assert event.text == "Short site walkthrough"
    assert event.media[0].platform_media_id == "video-file"
    assert event.media[0].content_type == "video/mp4"
    assert event.media[0].filename == "walkthrough.mp4"


def test_telegram_parser_handles_location_message():
    event = parse_telegram_update(
        {
            "message": {
                "message_id": 45,
                "chat": {"id": 1001},
                "from": {"id": 2002},
                "location": {"latitude": 6.5244, "longitude": 3.3792},
            }
        }
    )
    assert event.message_type == "location"
    assert event.location is not None
