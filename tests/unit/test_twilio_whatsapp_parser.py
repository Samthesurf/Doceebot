from datetime import UTC, datetime

import pytest

from whatsapp_ai_agent.integrations.whatsapp_twilio.parser import parse_twilio_whatsapp_form


def test_twilio_parser_handles_text_and_media():
    event = parse_twilio_whatsapp_form(
        {
            "MessageSid": "SM123",
            "From": "whatsapp:+2348012345678",
            "To": "whatsapp:+14155238886",
            "WaId": "2348012345678",
            "Body": "Installed inverter changeover",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/ME123",
            "MediaContentType0": "image/jpeg",
        },
        received_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    assert event.platform == "whatsapp_twilio"
    assert event.platform_message_id == "SM123"
    assert event.platform_user_id == "2348012345678"
    assert event.message_type == "image"
    assert event.media[0].content_type == "image/jpeg"
    assert event.text == "Installed inverter changeover"


def test_twilio_parser_handles_location_pin():
    event = parse_twilio_whatsapp_form(
        {
            "MessageSid": "SM124",
            "From": "whatsapp:+2348012345678",
            "NumMedia": "0",
            "Latitude": "6.5244",
            "Longitude": "3.3792",
            "Address": "Lagos",
            "Label": "Site office",
        },
        received_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    assert event.message_type == "location"
    assert event.location is not None
    assert event.location.label == "Site office"


def test_twilio_parser_rejects_missing_message_sid():
    with pytest.raises(ValueError):
        parse_twilio_whatsapp_form({"From": "whatsapp:+234"})
