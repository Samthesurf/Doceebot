from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.models import (
    ConversationSession,
    ConversationTurn,
    DeveloperEscalation,
    LlmAuditLog,
    RawInboundMessage,
    WorkLogEntry,
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

    def latest_previous_draft_snapshot(self, conversation_id: UUID) -> list[WorkLogDraft]:
        rows = self.session.scalars(
            select(ConversationTurn)
            .where(ConversationTurn.conversation_id == conversation_id)
            .order_by(ConversationTurn.occurred_at.desc(), ConversationTurn.created_at.desc())
            .limit(50)
        )
        for row in rows:
            metadata = _loads_json(row.metadata_json, {})
            if not isinstance(metadata, dict):
                continue
            snapshot = metadata.get("previous_drafts")
            if not isinstance(snapshot, list):
                continue
            return [WorkLogDraft.model_validate(item) for item in snapshot]
        return []

    def close_conversation(
        self,
        conversation: ConversationSession,
        *,
        status: str = "closed",
        closed_at: datetime | None = None,
    ) -> ConversationSession:
        conversation.status = status
        conversation.closed_at = closed_at or datetime.now(UTC)
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def export_payload(self, conversation_id: UUID) -> dict[str, object]:
        conversation = self.session.get(ConversationSession, conversation_id)
        turns = list(
            self.session.scalars(
                select(ConversationTurn)
                .where(ConversationTurn.conversation_id == conversation_id)
                .order_by(ConversationTurn.occurred_at.asc(), ConversationTurn.created_at.asc())
            )
        )
        work_logs = list(
            self.session.scalars(
                select(WorkLogEntry)
                .where(WorkLogEntry.conversation_id == conversation_id)
                .order_by(WorkLogEntry.work_date.asc(), WorkLogEntry.created_at.asc())
            )
        )
        audits = list(
            self.session.scalars(
                select(LlmAuditLog)
                .where(LlmAuditLog.conversation_id == conversation_id)
                .order_by(LlmAuditLog.created_at.asc())
            )
        )
        escalations = list(
            self.session.scalars(
                select(DeveloperEscalation)
                .where(DeveloperEscalation.conversation_id == conversation_id)
                .order_by(DeveloperEscalation.created_at.asc())
            )
        )
        return {
            "conversation": _conversation_payload(conversation),
            "turns": [_turn_payload(turn) for turn in turns],
            "work_logs": [_work_log_payload(log) for log in work_logs],
            "llm_audits": [_llm_audit_payload(audit) for audit in audits],
            "developer_escalations": [
                _developer_escalation_payload(row, include_snapshot=False) for row in escalations
            ],
        }

    def create_developer_escalation(
        self,
        *,
        conversation: ConversationSession,
        raw_message: RawInboundMessage | None,
        report_text: str,
        snapshot: dict[str, object] | None = None,
    ) -> DeveloperEscalation:
        payload = snapshot or self.export_payload(conversation.id)
        row = DeveloperEscalation(
            conversation_id=conversation.id,
            raw_message_id=raw_message.id if raw_message else None,
            org_id=conversation.org_id,
            user_id=conversation.user_id,
            platform=conversation.platform,
            report_text=report_text,
            conversation_snapshot_json=json.dumps(payload, default=str),
            status="pending",
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_developer_escalation_delivery(
        self,
        escalation: DeveloperEscalation,
        *,
        status: str,
        destination: str | None = None,
        provider_message_id: str | None = None,
        error_text: str | None = None,
    ) -> DeveloperEscalation:
        escalation.status = status
        escalation.destination = destination
        escalation.provider_message_id = provider_message_id
        escalation.error_text = error_text
        if status == "sent":
            escalation.sent_at = datetime.now(UTC)
        self.session.add(escalation)
        self.session.flush()
        return escalation

    def delete_conversation_data(self, conversation_id: UUID) -> None:
        raw_ids = list(
            self.session.scalars(
                select(RawInboundMessage.id).where(
                    RawInboundMessage.conversation_id == conversation_id
                )
            )
        )
        self.session.execute(
            delete(DeveloperEscalation).where(
                DeveloperEscalation.conversation_id == conversation_id
            )
        )
        self.session.execute(
            delete(LlmAuditLog).where(LlmAuditLog.conversation_id == conversation_id)
        )
        self.session.execute(
            delete(WorkLogEntry).where(WorkLogEntry.conversation_id == conversation_id)
        )
        self.session.execute(
            delete(ConversationTurn).where(ConversationTurn.conversation_id == conversation_id)
        )
        if raw_ids:
            self.session.execute(delete(RawInboundMessage).where(RawInboundMessage.id.in_(raw_ids)))
        self.session.execute(
            delete(ConversationSession).where(ConversationSession.id == conversation_id)
        )
        self.session.flush()


def _loads_json(value: str | None, fallback: object) -> object:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _dt(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _conversation_payload(conversation: ConversationSession | None) -> dict[str, object] | None:
    if conversation is None:
        return None
    return {
        "id": str(conversation.id),
        "org_id": str(conversation.org_id),
        "user_id": str(conversation.user_id),
        "platform": conversation.platform,
        "platform_chat_id": conversation.platform_chat_id,
        "status": conversation.status,
        "trigger": conversation.trigger,
        "title": conversation.title,
        "started_at": _dt(conversation.started_at),
        "last_message_at": _dt(conversation.last_message_at),
        "closed_at": _dt(conversation.closed_at),
        "created_at": _dt(conversation.created_at),
    }


def _turn_payload(turn: ConversationTurn) -> dict[str, object]:
    return {
        "id": str(turn.id),
        "raw_message_id": str(turn.raw_message_id) if turn.raw_message_id else None,
        "direction": turn.direction,
        "platform": turn.platform,
        "platform_message_id": turn.platform_message_id,
        "message_type": turn.message_type,
        "body_text": turn.body_text,
        "media": _loads_json(turn.media_json, []),
        "raw_payload": _loads_json(turn.raw_payload_json, {}),
        "metadata": _loads_json(turn.metadata_json, {}),
        "occurred_at": _dt(turn.occurred_at),
        "created_at": _dt(turn.created_at),
    }


def _work_log_payload(log: WorkLogEntry) -> dict[str, object]:
    return {
        "id": str(log.id),
        "raw_message_id": str(log.raw_message_id) if log.raw_message_id else None,
        "work_date": log.work_date.isoformat() if log.work_date else None,
        "start_time": log.start_time.isoformat() if log.start_time else None,
        "end_time": log.end_time.isoformat() if log.end_time else None,
        "timezone": log.timezone,
        "project": log.project,
        "site": log.site,
        "location_label": log.location_label,
        "location_address": log.location_address,
        "category": log.category,
        "title": log.title,
        "description": log.description,
        "summary": log.summary,
        "status": log.status,
        "confirmation_status": log.confirmation_status,
        "actions_taken": _loads_json(log.actions_taken_json, []),
        "participants": _loads_json(log.participants_json, []),
        "materials_used": _loads_json(log.materials_used_json, []),
        "equipment": _loads_json(log.equipment_json, []),
        "measurements": _loads_json(log.measurements_json, []),
        "blockers": _loads_json(log.blockers_json, []),
        "issues": _loads_json(log.issues_json, []),
        "safety_notes": _loads_json(log.safety_notes_json, []),
        "confidence": log.confidence,
        "created_at": _dt(log.created_at),
        "updated_at": _dt(log.updated_at),
    }


def _llm_audit_payload(audit: LlmAuditLog) -> dict[str, object]:
    return {
        "id": str(audit.id),
        "raw_message_id": str(audit.raw_message_id) if audit.raw_message_id else None,
        "provider": audit.provider,
        "model": audit.model,
        "purpose": audit.purpose,
        "input": _loads_json(audit.input_json, {}),
        "output": _loads_json(audit.output_json, None),
        "error_text": audit.error_text,
        "created_at": _dt(audit.created_at),
    }


def _developer_escalation_payload(
    escalation: DeveloperEscalation,
    *,
    include_snapshot: bool = True,
) -> dict[str, object]:
    payload = {
        "id": str(escalation.id),
        "raw_message_id": str(escalation.raw_message_id) if escalation.raw_message_id else None,
        "report_text": escalation.report_text,
        "status": escalation.status,
        "destination": escalation.destination,
        "provider_message_id": escalation.provider_message_id,
        "error_text": escalation.error_text,
        "created_at": _dt(escalation.created_at),
        "sent_at": _dt(escalation.sent_at),
    }
    if include_snapshot:
        payload["conversation_snapshot"] = _loads_json(
            escalation.conversation_snapshot_json,
            {},
        )
    return payload
