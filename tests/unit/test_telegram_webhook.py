from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.documents.schemas import DocumentAutomationResult, ManagedDocumentSummary
from whatsapp_ai_agent.integrations.telegram import webhook

TEXT_ACK = (
    "I received your work update. I will turn it into a draft log "
    "and ask for any missing details."
)


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
    assert webhook.build_acknowledgement(make_event()) == TEXT_ACK


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
            "text": TEXT_ACK,
        }
    ]


@pytest.mark.asyncio
async def test_send_document_result_files_sends_updated_local_file(tmp_path):
    storage_key = "orgs/org-1/managed/register.xlsx"
    local_file = tmp_path / storage_key
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"edited workbook bytes")
    sent_documents = []

    class FakeSender:
        async def send_document(self, *, chat_id, path, caption=None):
            sent_documents.append(
                {
                    "chat_id": chat_id,
                    "filename": path.name,
                    "bytes": path.read_bytes(),
                    "caption": caption,
                }
            )

    result = DocumentAutomationResult(
        document=ManagedDocumentSummary(
            id="doc-1",
            org_id="org-1",
            filename="register.xlsx",
            display_name="Register",
            document_kind="xlsx",
            source_type="uploaded",
            status="available",
            storage_backend="local",
            storage_key=storage_key,
        ),
        action="updated",
        rows_applied=1,
        changes=["Updated row 6 in sheet Field Register."],
    )

    await webhook.send_document_result_files(
        sender=FakeSender(),
        chat_id="1001",
        results=[result],
        settings=Settings(local_storage_dir=str(tmp_path), _env_file=None),
    )

    assert sent_documents == [
        {
            "chat_id": "1001",
            "filename": "register.xlsx",
            "bytes": b"edited workbook bytes",
            "caption": (
                "Edited file: register.xlsx\n"
                "Status: updated; 1 row(s) applied.\n"
                "Changes:\n"
                "- Updated row 6 in sheet Field Register.\n"
                "Open this attachment to see the actual edited document."
            ),
        }
    ]


@pytest.mark.asyncio
async def test_receive_telegram_update_sends_text_then_edited_file(monkeypatch, tmp_path):
    storage_key = "orgs/org-1/managed/register.xlsx"
    local_file = tmp_path / storage_key
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"edited workbook bytes")
    sent_texts = []
    sent_documents = []

    result = DocumentAutomationResult(
        document=ManagedDocumentSummary(
            id="doc-1",
            org_id="org-1",
            filename="register.xlsx",
            display_name="Register",
            document_kind="xlsx",
            source_type="uploaded",
            status="available",
            storage_backend="local",
            storage_key=storage_key,
        ),
        action="updated",
        rows_applied=1,
        changes=["Updated row 6 in sheet Field Register."],
    )

    class FakeSender:
        def __init__(self, *, settings):
            self.settings = settings

        async def send_text(self, *, chat_id, text):
            sent_texts.append({"chat_id": chat_id, "text": text})

        async def send_document(self, *, chat_id, path, caption=None):
            sent_documents.append(
                {
                    "chat_id": chat_id,
                    "filename": path.name,
                    "bytes": path.read_bytes(),
                    "caption": caption,
                }
            )

    async def fake_process_result(event, *, settings, db_session):
        return webhook.TelegramProcessingOutcome(
            reply_text="Document automation:\n- Updated: register.xlsx (1 row(s))",
            document_results=[result],
        )

    monkeypatch.setattr(
        webhook,
        "parse_telegram_update",
        lambda update, timezone_name: make_event(),
    )
    monkeypatch.setattr(webhook, "process_live_telegram_event_result", fake_process_result)
    monkeypatch.setattr(webhook, "TelegramSender", FakeSender)
    request = SimpleNamespace(headers={}, app=SimpleNamespace(state=SimpleNamespace()))

    response = await webhook.receive_telegram_update(
        {"message": {"message_id": 42}},
        request,
        settings=Settings(local_storage_dir=str(tmp_path), _env_file=None),
        db_session=object(),
    )

    assert response == {"status": "accepted"}
    assert sent_texts == [
        {
            "chat_id": "1001",
            "text": "Document automation:\n- Updated: register.xlsx (1 row(s))",
        }
    ]
    assert sent_documents[0]["chat_id"] == "1001"
    assert sent_documents[0]["filename"] == "register.xlsx"
    assert sent_documents[0]["bytes"] == b"edited workbook bytes"
