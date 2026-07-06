import json
from datetime import UTC, datetime, time
from typing import Literal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.models import (
    Base,
    ConversationSession,
    ConversationTurn,
    DeveloperEscalation,
    RawInboundMessage,
    WorkLogEntry,
)
from whatsapp_ai_agent.llm.schemas import ChatParseResult, ReportRequest, WorkLogDraft
from whatsapp_ai_agent.memory.conversation_commands import parse_conversation_command
from whatsapp_ai_agent.workflows.chat_processing import process_inbound_event


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as session:
        yield session


def make_event(
    text: str | None,
    *,
    sid: str | None = None,
    received_at: datetime | None = None,
    message_type: Literal[
        "text",
        "voice",
        "audio",
        "image",
        "document",
        "location",
        "unknown",
    ] = "text",
    raw_payload: dict[str, object] | None = None,
) -> InboundEvent:
    return InboundEvent(
        platform="whatsapp_twilio",
        platform_message_id=sid or f"SM{uuid4().hex[:12]}",
        platform_user_id="2348012345678",
        platform_chat_id="whatsapp:+234****5678",
        message_type=message_type,
        text=text,
        received_at=received_at or datetime(2026, 7, 6, 10, 0, tzinfo=UTC),
        local_date="2026-07-06",
        local_time="11:00:00",
        timezone="Africa/Lagos",
        raw_payload=raw_payload or {},
    )


class QueueNormalizer:
    def __init__(self, results: list[ChatParseResult]) -> None:
        self.results = list(results)
        self.contexts = []
        self.events = []

    async def parse_chat_event(self, event, *, media_extractions=None, conversation_context=None):
        self.events.append(event)
        self.contexts.append(conversation_context)
        if not self.results:
            raise AssertionError("normalizer should not have been called")
        return self.results.pop(0)


def log(title: str, *, project: str | None = None) -> WorkLogDraft:
    return WorkLogDraft(
        work_date=datetime(2026, 7, 6).date(),
        start_time=time(10, 0),
        end_time=time(17, 0),
        project=project,
        title=title,
        description=f"Description for {title}",
        participants=["Fable"],
        actions_taken=[f"Action for {title}"],
        materials_used=["Spanner"],
        confidence=0.9,
    )


def result(*logs: WorkLogDraft, report: bool = False) -> ChatParseResult:
    if report:
        return ChatParseResult(
            intent="report_request",
            report_request=ReportRequest(report_type="daily", title="Daily report"),
            summary_for_user="report requested",
            confidence=0.9,
        )
    return ChatParseResult(
        intent="work_log" if logs else "other",
        work_logs=list(logs),
        summary_for_user="parsed" if logs else "other",
        confidence=0.9,
    )


async def seed_session(db_session, *logs: WorkLogDraft, normalizer: QueueNormalizer | None = None):
    org_id = uuid4()
    user_id = uuid4()
    normalizer = normalizer or QueueNormalizer([result(*logs)])
    first = await process_inbound_event(
        make_event("Initial work update", sid="SMSEED"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )
    return org_id, user_id, first.conversation_id, normalizer


@pytest.mark.asyncio
async def test_01_help_command_returns_capabilities_without_llm(db_session):
    reply = await process_inbound_event(
        make_event("help"),
        org_id=uuid4(),
        user_id=uuid4(),
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert "Core commands" in reply.reply_text
    assert "report this <problem>" in reply.reply_text
    outbound = db_session.scalar(
        select(ConversationTurn).where(ConversationTurn.direction == "outbound")
    )
    assert outbound


@pytest.mark.asyncio
async def test_02_status_command_shows_empty_draft_board(db_session):
    reply = await process_inbound_event(
        make_event("status"),
        org_id=uuid4(),
        user_id=uuid4(),
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert "Current work-log session drafts" in reply.reply_text
    assert "No active draft logs yet" in reply.reply_text


@pytest.mark.asyncio
async def test_03_status_command_lists_existing_drafts(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("DB dressing"), log("Cable tray"))

    reply = await process_inbound_event(
        make_event("show drafts"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert "1. DB dressing" in reply.reply_text
    assert "2. Cable tray" in reply.reply_text


@pytest.mark.asyncio
async def test_04_confirm_one_only_confirms_selected_draft(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"), log("B"))

    reply = await process_inbound_event(
        make_event("confirm 1"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    entries = list(db_session.scalars(select(WorkLogEntry).order_by(WorkLogEntry.created_at)))
    assert "Confirmed 1 selected" in reply.reply_text
    assert [entry.confirmation_status for entry in entries] == ["confirmed", "draft"]


@pytest.mark.asyncio
async def test_05_confirm_all_confirms_all_drafts(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"), log("B"))

    await process_inbound_event(
        make_event("confirm all"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert {entry.confirmation_status for entry in db_session.scalars(select(WorkLogEntry))} == {
        "confirmed"
    }


@pytest.mark.asyncio
async def test_06_delete_one_removes_selected_draft(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"), log("B"), log("C"))

    reply = await process_inbound_event(
        make_event("delete 2"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    titles = [entry.title for entry in db_session.scalars(select(WorkLogEntry))]
    assert "Deleted 1" in reply.reply_text
    assert titles == ["A", "C"]


@pytest.mark.asyncio
async def test_07_delete_without_index_asks_for_target(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))

    reply = await process_inbound_event(
        make_event("delete"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert "which draft to delete" in reply.reply_text
    assert db_session.scalar(select(WorkLogEntry)).title == "A"


@pytest.mark.asyncio
async def test_08_merge_combines_two_drafts(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"), log("B"))

    reply = await process_inbound_event(
        make_event("merge 1 and 2"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    entries = list(db_session.scalars(select(WorkLogEntry)))
    assert "Merged" in reply.reply_text
    assert len(entries) == 1
    assert "A" in entries[0].title and "B" in entries[0].title


@pytest.mark.asyncio
async def test_09_merge_requires_two_indexes(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))

    reply = await process_inbound_event(
        make_event("merge 1"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert "at least two drafts" in reply.reply_text


@pytest.mark.asyncio
async def test_10_edit_command_uses_conversation_context_and_updates_draft(db_session):
    updated = log("A updated", project="Main project")
    normalizer = QueueNormalizer([result(log("A")), result(updated)])
    org_id, user_id, _, normalizer = await seed_session(db_session, log("A"), normalizer=normalizer)

    reply = await process_inbound_event(
        make_event("edit 1: project is Main project"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )

    assert "Main project" in reply.reply_text
    assert normalizer.contexts[-1] is not None
    assert normalizer.contexts[-1].recent_turns[-1]["message_type"] == "command_hint"
    assert db_session.scalar(select(WorkLogEntry)).project == "Main project"


@pytest.mark.asyncio
async def test_11_split_command_can_replace_one_draft_with_multiple_drafts(db_session):
    normalizer = QueueNormalizer([result(log("A")), result(log("A1"), log("A2"))])
    org_id, user_id, _, normalizer = await seed_session(db_session, log("A"), normalizer=normalizer)

    await process_inbound_event(
        make_event("split 1: make separate logs for morning and afternoon"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )

    assert [entry.title for entry in db_session.scalars(select(WorkLogEntry))] == ["A1", "A2"]


@pytest.mark.asyncio
async def test_12_undo_restores_previous_draft_board(db_session):
    normalizer = QueueNormalizer([result(log("Before")), result(log("After"))])
    org_id, user_id, _, normalizer = await seed_session(
        db_session,
        log("Before"),
        normalizer=normalizer,
    )
    await process_inbound_event(
        make_event("edit 1: change title to After"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )

    reply = await process_inbound_event(
        make_event("undo"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert "Restored" in reply.reply_text
    assert [entry.title for entry in db_session.scalars(select(WorkLogEntry))] == ["Before"]


@pytest.mark.asyncio
async def test_13_cancel_closes_session_and_cancels_drafts(db_session):
    org_id, user_id, conversation_id, _ = await seed_session(db_session, log("A"))

    reply = await process_inbound_event(
        make_event("cancel"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    session = db_session.get(ConversationSession, conversation_id)
    entry = db_session.scalar(select(WorkLogEntry))
    assert "Cancelled" in reply.reply_text
    assert session.status == "cancelled"
    assert entry.confirmation_status == "cancelled"


@pytest.mark.asyncio
async def test_14_export_writes_audit_bundle(db_session, tmp_path):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))
    settings = Settings(developer_escalation_storage_dir=str(tmp_path), _env_file=None)

    reply = await process_inbound_event(
        make_event("export"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        settings=settings,
        store_reports=False,
    )

    assert "Conversation export is ready" in reply.reply_text
    assert list(tmp_path.glob("conversation-*.json"))


@pytest.mark.asyncio
async def test_15_forget_deletes_conversation_data(db_session):
    org_id, user_id, conversation_id, _ = await seed_session(db_session, log("A"))

    reply = await process_inbound_event(
        make_event("forget this session"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert "Deleted stored data" in reply.reply_text
    assert db_session.get(ConversationSession, conversation_id) is None
    assert list(db_session.scalars(select(WorkLogEntry))) == []
    assert list(db_session.scalars(select(RawInboundMessage))) == []


@pytest.mark.asyncio
async def test_16_report_creates_developer_escalation_with_snapshot(db_session, tmp_path):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))
    settings = Settings(developer_escalation_storage_dir=str(tmp_path), _env_file=None)

    reply = await process_inbound_event(
        make_event("report this bot keeps disagreeing with me about the time"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        settings=settings,
        store_reports=False,
    )

    escalation = db_session.scalar(select(DeveloperEscalation))
    snapshot = json.loads(escalation.conversation_snapshot_json)
    bundle_path = next(tmp_path.glob("*.json"))
    bundle_snapshot = json.loads(bundle_path.read_text())
    assert "Reported this conversation to the developer" in reply.reply_text
    assert "keeps disagreeing" in escalation.report_text
    assert escalation.status == "pending"
    assert "work_logs" in snapshot
    assert snapshot["llm_audits_redacted"] is True
    assert "llm_audits" not in snapshot
    assert snapshot["llm_audit_summary"]
    assert "input" not in snapshot["llm_audit_summary"][0]
    assert "output" not in snapshot["llm_audit_summary"][0]
    assert snapshot["turns"][0]["raw_payload_redacted"] is True
    assert "raw_payload" not in snapshot["turns"][0]
    assert bundle_snapshot == snapshot


@pytest.mark.asyncio
async def test_17_admin_request_maps_to_developer_escalation(db_session, tmp_path):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))
    settings = Settings(developer_escalation_storage_dir=str(tmp_path), _env_file=None)

    await process_inbound_event(
        make_event("admin"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        settings=settings,
        store_reports=False,
    )

    assert db_session.scalar(select(DeveloperEscalation)).report_text.startswith("User requested")


@pytest.mark.asyncio
async def test_18_wrong_feedback_is_logged_without_llm(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))

    reply = await process_inbound_event(
        make_event("wrong"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    turns = list(db_session.scalars(select(ConversationTurn).order_by(ConversationTurn.created_at)))
    assert "marked the last response as wrong" in reply.reply_text
    assert any('"command": "feedback"' in turn.metadata_json for turn in turns)


@pytest.mark.asyncio
async def test_19_report_for_this_week_still_reaches_report_parser(db_session):
    normalizer = QueueNormalizer([result(report=True)])
    reply = await process_inbound_event(
        make_event("report for this week"),
        org_id=uuid4(),
        user_id=uuid4(),
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )

    assert normalizer.events
    assert "Daily report" in reply.reply_text
    assert db_session.scalar(select(DeveloperEscalation)) is None


@pytest.mark.asyncio
async def test_20_new_spanner_does_not_trigger_new_session_command(db_session):
    normalizer = QueueNormalizer([result(log("A")), result(log("B"))])
    org_id, user_id, first_conversation_id, normalizer = await seed_session(
        db_session,
        log("A"),
        normalizer=normalizer,
    )

    reply = await process_inbound_event(
        make_event("new spanner was collected"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )

    assert reply.conversation_id == first_conversation_id
    assert normalizer.events[-1].text == "new spanner was collected"
    assert [entry.title for entry in db_session.scalars(select(WorkLogEntry))] == ["B"]


def test_21_command_parser_does_not_steal_plain_report_requests():
    assert parse_conversation_command(make_event("report for last week")) is None
    assert parse_conversation_command(make_event("report: bot is looping")).name == "report"


def test_22_command_parser_ignores_non_text_messages():
    assert parse_conversation_command(make_event("help", message_type="voice")) is None


@pytest.mark.asyncio
async def test_23_positive_feedback_is_logged_without_llm(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))

    reply = await process_inbound_event(
        make_event("good"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    turns = list(db_session.scalars(select(ConversationTurn).order_by(ConversationTurn.created_at)))
    metadata = [json.loads(turn.metadata_json or "{}") for turn in turns]
    assert "positive" in reply.reply_text
    assert any(item.get("command") == "feedback" for item in metadata)


@pytest.mark.asyncio
async def test_24_undo_without_previous_snapshot_tells_user(db_session):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))

    reply = await process_inbound_event(
        make_event("undo"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        store_reports=False,
    )

    assert "do not have a previous draft board" in reply.reply_text
    assert [entry.title for entry in db_session.scalars(select(WorkLogEntry))] == ["A"]


@pytest.mark.asyncio
async def test_25_report_delivery_failure_is_recorded(db_session, tmp_path):
    org_id, user_id, _, _ = await seed_session(db_session, log("A"))
    settings = Settings(
        developer_escalation_storage_dir=str(tmp_path),
        developer_escalation_telegram_chat_id="12345",
        telegram_bot_token=None,
        _env_file=None,
    )

    reply = await process_inbound_event(
        make_event("report: delivery should fail"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=QueueNormalizer([]),
        settings=settings,
        store_reports=False,
    )

    escalation = db_session.scalar(select(DeveloperEscalation))
    assert "live delivery to the developer failed" in reply.reply_text
    assert escalation.status == "failed"
    assert escalation.destination == "telegram:12345"
    assert "TELEGRAM_BOT_TOKEN" in escalation.error_text


@pytest.mark.asyncio
async def test_26_process_inbound_requires_resolved_org_and_user():
    with pytest.raises(PermissionError):
        await process_inbound_event(
            make_event("help"),
            normalizer=QueueNormalizer([]),
            store_reports=False,
        )