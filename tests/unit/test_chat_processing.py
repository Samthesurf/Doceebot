from datetime import UTC, datetime
from uuid import uuid4

import pytest

from whatsapp_ai_agent.core.events import InboundEvent, MediaRef
from whatsapp_ai_agent.llm.schemas import ChatParseResult, WorkLogDraft
from whatsapp_ai_agent.workflows.chat_processing import _is_greeting, process_inbound_event


class FakeNormalizer:
    async def parse_chat_event(self, event, *, media_extractions=None):
        return ChatParseResult(
            intent="work_log",
            work_logs=[
                WorkLogDraft(
                    work_date=event.local_date,
                    timezone=event.timezone,
                    project="Lekki inverter room",
                    site="Lekki branch",
                    title="DB dressing and continuity test",
                    description=(
                        "The worker dressed the distribution board "
                        "and tested breaker continuity."
                    ),
                    actions_taken=["Dressed the DB", "Tested breaker continuity"],
                    materials_used=["Cable ties", "Labels"],
                    status="done",
                    confidence=0.88,
                    source_event_ids=[event.platform_message_id],
                )
            ],
            follow_up_questions=["What time did the work finish?"],
            summary_for_user="Logged DB dressing and continuity testing.",
            needs_user_confirmation=True,
            confidence=0.88,
        )


def make_event(**overrides):
    values = {
        "platform": "telegram",
        "platform_message_id": "1001:42",
        "platform_user_id": "2002",
        "platform_chat_id": "1001",
        "message_type": "text",
        "text": "Today we dressed the DB at Lekki and tested breaker continuity.",
        "received_at": datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        "local_date": "2026-07-01",
        "local_time": "11:00:00",
        "timezone": "Africa/Lagos",
        "raw_payload": {},
    }
    values.update(overrides)
    return InboundEvent(**values)


@pytest.mark.asyncio
async def test_process_inbound_event_builds_draft_reply_with_follow_up_questions():
    result = await process_inbound_event(
        make_event(),
        org_id=uuid4(),
        user_id=uuid4(),
        normalizer=FakeNormalizer(),
        store_reports=False,
    )

    assert len(result.work_logs) == 1
    assert result.work_logs[0].project == "Lekki inverter room"
    assert "I parsed this and saved it as a draft work log" in result.reply_text
    assert "DB dressing and continuity test" in result.reply_text
    assert "What time did the work finish?" in result.reply_text
    assert "Reply confirm" not in result.reply_text


@pytest.mark.asyncio
async def test_process_inbound_upload_uses_upload_nicety():
    event = make_event(
        message_type="document",
        text="Please log this site update from the attached note.",
        media=[
            MediaRef(
                platform_media_id="file-1",
                filename="site-note.txt",
                content_type="text/plain",
                size_bytes=42,
            )
        ],
    )

    result = await process_inbound_event(
        event,
        org_id=uuid4(),
        user_id=uuid4(),
        normalizer=FakeNormalizer(),
        store_reports=False,
    )

    assert result.reply_text.startswith("I uploaded and parsed site-note.txt.")
    assert "A few quick checks" in result.reply_text


@pytest.mark.asyncio
async def test_process_inbound_event_requires_tenant_scope_before_ai():
    with pytest.raises(PermissionError):
        await process_inbound_event(
            make_event(),
            normalizer=FakeNormalizer(),
            store_reports=False,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "greeting",
    ["hi", "Hi", "hiii", "hello", "Hellooo", "hey", "HEY", "yo", "good morning", "good evening"],
)
async def test_process_inbound_event_replies_warmly_to_greetings(greeting):
    result = await process_inbound_event(
        make_event(text=greeting),
        org_id=uuid4(),
        user_id=uuid4(),
        normalizer=FakeNormalizer(),
        store_reports=False,
    )

    assert result.reply_text
    assert "I may be misunderstanding" not in result.reply_text
    assert "Worker sent a greeting" not in result.reply_text
    assert result.reply_text[0].isupper()


@pytest.mark.asyncio
async def test_process_inbound_event_greeting_does_not_call_normalizer():
    calls = []

    class RecordingNormalizer:
        async def parse_chat_event(self, event, *, media_extractions=None):
            calls.append(event)
            raise AssertionError("greeting should not reach the LLM normalizer")

    await process_inbound_event(
        make_event(text="Hellooo"),
        org_id=uuid4(),
        user_id=uuid4(),
        normalizer=RecordingNormalizer(),
        store_reports=False,
    )

    assert calls == []


def test_greeting_helper_classifies_common_cases():
    assert _is_greeting("hi")
    assert _is_greeting("Hellooo")
    assert _is_greeting("good afternoon")
    assert not _is_greeting("Completed DB dressing")
    assert not _is_greeting("hi there can you log this")
    assert not _is_greeting("")
