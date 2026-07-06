from datetime import UTC, datetime, time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.models import (
    Base,
    ConversationSession,
    ConversationTurn,
    LlmAuditLog,
    WorkLogEntry,
)
from whatsapp_ai_agent.llm.schemas import ChatParseResult, WorkLogDraft
from whatsapp_ai_agent.memory.work_logs import build_confirmation_message
from whatsapp_ai_agent.workflows.chat_processing import process_inbound_event


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as session:
        yield session


def make_event(**overrides: object) -> InboundEvent:
    received_at = overrides.pop("received_at", datetime(2026, 7, 6, 10, 0, tzinfo=UTC))
    values = {
        "platform": "whatsapp_twilio",
        "platform_message_id": "SM1",
        "platform_user_id": "2348012345678",
        "platform_chat_id": "whatsapp:+2348012345678",
        "message_type": "text",
        "text": "Went to the field with Fable and Israel from 10 to 5.",
        "received_at": received_at,
        "local_date": "2026-07-06",
        "local_time": "11:00:00",
        "timezone": "Africa/Lagos",
        "raw_payload": {},
    }
    values.update(overrides)
    return InboundEvent(**values)


class QueueNormalizer:
    def __init__(self, results: list[ChatParseResult]) -> None:
        self.results = list(results)
        self.contexts = []

    async def parse_chat_event(self, event, *, media_extractions=None, conversation_context=None):
        self.contexts.append(conversation_context)
        return self.results.pop(0)


def parse_result(log: WorkLogDraft, *, questions: list[str] | None = None) -> ChatParseResult:
    return ChatParseResult(
        intent="work_log",
        work_logs=[log],
        summary_for_user=log.title,
        follow_up_questions=questions or [],
        confidence=log.confidence,
    )


@pytest.mark.asyncio
async def test_follow_up_updates_same_conversation_without_duplicate_logs(db_session):
    org_id = uuid4()
    user_id = uuid4()
    first_log = WorkLogDraft(
        work_date=datetime(2026, 7, 6).date(),
        start_time=time(10, 0),
        end_time=time(17, 0),
        title="Field spanner retrieval",
        description="Picked up spanners from the field.",
        participants=["Fable", "Israel"],
        actions_taken=["Picked up spanners"],
        confidence=0.9,
    )
    updated_log = first_log.model_copy(
        update={
            "site": "Oron sea port",
            "materials_used": ["Spanners (9)", "Toolbox", "Bucket"],
            "safety_notes": ["Gloves worn"],
            "description": "Picked up 9 spanners and tools from Oron sea port.",
        }
    )
    normalizer = QueueNormalizer(
        [
            parse_result(first_log, questions=["What site was this for?"]),
            parse_result(updated_log, questions=["Who participated?", "What time did it happen?"]),
        ]
    )

    first = await process_inbound_event(
        make_event(platform_message_id="SM1"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )
    second = await process_inbound_event(
        make_event(
            platform_message_id="SM2",
            text=(
                "This happened in Oron sea port. 9 spanners, the toolbox and a bucket "
                "were used. We wore gloves."
            ),
            received_at=datetime(2026, 7, 6, 10, 5, tzinfo=UTC),
        ),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )

    assert first.conversation_id == second.conversation_id
    assert normalizer.contexts[0] is None
    assert normalizer.contexts[1] is not None
    assert len(normalizer.contexts[1].previous_work_logs) == 1

    entries = list(db_session.scalars(select(WorkLogEntry)))
    assert len(entries) == 1
    assert entries[0].conversation_id == first.conversation_id
    assert entries[0].site == "Oron sea port"
    assert entries[0].participants_json == '["Fable", "Israel"]'
    assert "Who participated?" not in second.reply_text
    assert "What time did it happen?" not in second.reply_text
    assert "People: Fable; Israel" in second.reply_text
    assert "Time: 10:00 to 17:00" in second.reply_text
    assert "Materials: Spanners (9); Toolbox; Bucket" in second.reply_text

    turns = list(db_session.scalars(select(ConversationTurn)))
    audits = list(db_session.scalars(select(LlmAuditLog)))
    assert [turn.direction for turn in turns] == ["inbound", "outbound", "inbound", "outbound"]
    assert len(audits) == 2


@pytest.mark.asyncio
async def test_new_command_starts_fresh_conversation_without_parsing(db_session):
    org_id = uuid4()
    user_id = uuid4()
    log = WorkLogDraft(
        work_date=datetime(2026, 7, 6).date(),
        title="Initial log",
        description="Initial log",
        confidence=0.8,
    )
    normalizer = QueueNormalizer([parse_result(log)])

    first = await process_inbound_event(
        make_event(platform_message_id="SM1"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )
    new_reply = await process_inbound_event(
        make_event(
            platform_message_id="SMNEW",
            text="new",
            received_at=datetime(2026, 7, 6, 10, 10, tzinfo=UTC),
        ),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )

    sessions = list(
        db_session.scalars(select(ConversationSession).order_by(ConversationSession.started_at))
    )
    assert len(sessions) == 2
    assert first.conversation_id == sessions[0].id
    assert sessions[0].status == "closed"
    assert new_reply.conversation_id == sessions[1].id
    assert "Started a new work-log conversation" in new_reply.reply_text
    assert normalizer.results == []


@pytest.mark.asyncio
async def test_idle_timeout_after_13_hours_starts_fresh_conversation(db_session):
    org_id = uuid4()
    user_id = uuid4()
    log_a = WorkLogDraft(
        work_date=datetime(2026, 7, 6).date(),
        title="Morning log",
        description="Morning log",
        confidence=0.8,
    )
    log_b = WorkLogDraft(
        work_date=datetime(2026, 7, 7).date(),
        title="Next day log",
        description="Next day log",
        confidence=0.8,
    )
    normalizer = QueueNormalizer([parse_result(log_a), parse_result(log_b)])

    first = await process_inbound_event(
        make_event(platform_message_id="SM1"),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )
    second = await process_inbound_event(
        make_event(
            platform_message_id="SM2",
            received_at=datetime(2026, 7, 7, 0, 1, tzinfo=UTC),
            local_date="2026-07-07",
            text="New work after a long gap.",
        ),
        org_id=org_id,
        user_id=user_id,
        db_session=db_session,
        normalizer=normalizer,
        store_reports=False,
    )

    assert first.conversation_id != second.conversation_id
    assert normalizer.contexts[1] is None
    sessions = list(db_session.scalars(select(ConversationSession)))
    assert len(sessions) == 2


def test_confirmation_message_shows_extracted_details_and_filters_answered_questions():
    log = WorkLogDraft(
        work_date=datetime(2026, 7, 6).date(),
        start_time=time(10, 0),
        end_time=time(17, 0),
        title="Field spanner retrieval",
        description="Picked up spanners.",
        participants=["Fable", "Israel", "Debora"],
        actions_taken=["Picked up spanners"],
        materials_used=["Spanners (9)"],
        safety_notes=["Gloves worn"],
        confidence=0.95,
    )
    message = build_confirmation_message(
        parse_result(
            log,
            questions=[
                "Who participated?",
                "What time did this start and end?",
                "What project was this for?",
            ],
        )
    )

    assert "People: Fable; Israel; Debora" in message
    assert "Time: 10:00 to 17:00" in message
    assert "Materials: Spanners (9)" in message
    assert "Safety: Gloves worn" in message
    assert "Who participated?" not in message
    assert "What time did this start and end?" not in message
    assert "What project was this for?" in message
