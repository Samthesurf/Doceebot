from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.models import (
    ConversationSession,
    ConversationTurn,
    LlmAuditLog,
    RawInboundMessage,
)
from whatsapp_ai_agent.llm.schemas import WorkLogDraft

CONVERSATION_IDLE_HOURS = 13
_NEW_CONVERSATION_COMMANDS = {"new", "/new", "new log", "new conversation", "start new"}
_CONFIRM_COMMANDS = {
    "confirm",
    "confirmed",
    "correct",
    "yes correct",
    "yes, correct",
    "that's correct",
}


def _event_time(event: InboundEvent) -> datetime:
    return event.received_at or datetime.now(UTC)


def _align_timezones(later: datetime, earlier: datetime) -> tuple[datetime, datetime]:
    if later.tzinfo is not None and earlier.tzinfo is None:
        return later, earlier.replace(tzinfo=later.tzinfo)
    if later.tzinfo is None and earlier.tzinfo is not None:
        return later.replace(tzinfo=earlier.tzinfo), earlier
    return later, earlier


def _normalized_text(event: InboundEvent) -> str:
    return " ".join((event.text or "").strip().lower().split())


def starts_new_conversation(event: InboundEvent) -> bool:
    return event.message_type == "text" and _normalized_text(event) in _NEW_CONVERSATION_COMMANDS


def confirms_conversation(event: InboundEvent) -> bool:
    return event.message_type == "text" and _normalized_text(event) in _CONFIRM_COMMANDS


@dataclass(frozen=True)
class ConversationContext:
    session_id: str
    started_at: str | None
    last_message_at: str | None
    previous_work_logs: list[WorkLogDraft] = field(default_factory=list)
    recent_turns: list[dict[str, object]] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "last_message_at": self.last_message_at,
            "previous_work_logs": [
                log.model_dump(mode="json") for log in self.previous_work_logs
            ],
            "recent_turns": self.recent_turns,
        }


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_for_event(
        self,
        event: InboundEvent,
        *,
        force_new: bool = False,
        idle_hours: int = CONVERSATION_IDLE_HOURS,
    ) -> tuple[ConversationSession, bool]:
        if event.org_id is None or event.user_id is None:
            raise ValueError("event must have org_id and user_id before conversation resolution")

        event_time = _event_time(event)
        active = self.session.scalar(
            select(ConversationSession)
            .where(
                ConversationSession.org_id == event.org_id,
                ConversationSession.user_id == event.user_id,
                ConversationSession.platform == event.platform,
                ConversationSession.platform_chat_id == event.platform_chat_id,
                ConversationSession.status == "active",
            )
            .order_by(ConversationSession.last_message_at.desc())
            .limit(1)
        )
        stale = False
        if active is not None and active.last_message_at is not None:
            later, earlier = _align_timezones(event_time, active.last_message_at)
            stale = later - earlier > timedelta(hours=idle_hours)

        if active is not None and (force_new or stale):
            active.status = "closed"
            active.closed_at = event_time
            self.session.add(active)
            active = None

        if active is not None:
            active.last_message_at = event_time
            self.session.add(active)
            self.session.flush()
            return active, False

        session = ConversationSession(
            org_id=event.org_id,
            user_id=event.user_id,
            platform=event.platform,
            platform_chat_id=event.platform_chat_id,
            status="active",
            trigger="manual_new" if force_new else ("idle_timeout" if stale else "first_message"),
            started_at=event_time,
            last_message_at=event_time,
        )
        self.session.add(session)
        self.session.flush()
        return session, True

    def recent_turn_payloads(
        self,
        conversation_id: UUID,
        *,
        limit: int = 12,
    ) -> list[dict[str, object]]:
        rows = list(
            self.session.scalars(
                select(ConversationTurn)
                .where(ConversationTurn.conversation_id == conversation_id)
                .order_by(ConversationTurn.occurred_at.desc(), ConversationTurn.created_at.desc())
                .limit(limit)
            )
        )
        rows.reverse()
        payloads: list[dict[str, object]] = []
        for row in rows:
            payloads.append(
                {
                    "direction": row.direction,
                    "message_type": row.message_type,
                    "body_text": row.body_text,
                    "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                    "metadata": _loads_json(row.metadata_json, {}),
                }
            )
        return payloads

    def log_turn(
        self,
        conversation: ConversationSession,
        *,
        direction: str,
        body_text: str | None,
        occurred_at: datetime,
        raw_message: RawInboundMessage | None = None,
        platform: str | None = None,
        platform_message_id: str | None = None,
        message_type: str | None = None,
        media: list[dict[str, object]] | None = None,
        raw_payload: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            conversation_id=conversation.id,
            raw_message_id=raw_message.id if raw_message else None,
            direction=direction,
            platform=platform,
            platform_message_id=platform_message_id,
            message_type=message_type,
            body_text=body_text,
            media_json=json.dumps(media or [], default=str),
            raw_payload_json=json.dumps(raw_payload or {}, default=str),
            metadata_json=json.dumps(metadata or {}, default=str),
            occurred_at=occurred_at,
        )
        if direction == "inbound":
            conversation.last_message_at = occurred_at
        self.session.add_all([conversation, turn])
        self.session.flush()
        return turn

    def log_inbound_event(
        self,
        conversation: ConversationSession,
        event: InboundEvent,
        *,
        raw_message: RawInboundMessage | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ConversationTurn:
        return self.log_turn(
            conversation,
            direction="inbound",
            body_text=event.text,
            occurred_at=_event_time(event),
            raw_message=raw_message,
            platform=event.platform,
            platform_message_id=event.platform_message_id,
            message_type=event.message_type,
            media=[media.model_dump(mode="json") for media in event.media],
            raw_payload=dict(event.raw_payload),
            metadata=metadata,
        )

    def log_outbound_reply(
        self,
        conversation: ConversationSession,
        *,
        body_text: str,
        platform: str | None = None,
        provider_message_id: str | None = None,
        occurred_at: datetime | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ConversationTurn:
        payload = dict(metadata or {})
        if provider_message_id:
            payload["provider_message_id"] = provider_message_id
        return self.log_turn(
            conversation,
            direction="outbound",
            body_text=body_text,
            occurred_at=occurred_at or datetime.now(UTC),
            platform=platform,
            platform_message_id=provider_message_id,
            message_type="text",
            metadata=payload,
        )

    def log_llm_audit(
        self,
        *,
        conversation: ConversationSession | None,
        raw_message: RawInboundMessage | None = None,
        provider: str,
        model: str,
        purpose: str,
        input_payload: dict[str, object],
        output_payload: dict[str, object] | list[object] | None = None,
        error_text: str | None = None,
    ) -> LlmAuditLog:
        row = LlmAuditLog(
            conversation_id=conversation.id if conversation else None,
            raw_message_id=raw_message.id if raw_message else None,
            provider=provider,
            model=model,
            purpose=purpose,
            input_json=json.dumps(input_payload, default=str),
            output_json=(
                json.dumps(output_payload, default=str) if output_payload is not None else None
            ),
            error_text=error_text,
        )
        self.session.add(row)
        self.session.flush()
        return row


def _loads_json(value: str | None, fallback: object) -> object:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
