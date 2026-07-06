import json
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from whatsapp_ai_agent.db.models import RawInboundMessage, WorkLogEntry
from whatsapp_ai_agent.llm.schemas import ChatParseResult, NormalizedWorkLog, WorkLogDraft


@dataclass
class InMemoryWorkLogStore:
    entries: list[WorkLogDraft] = field(default_factory=list)

    def add_many(self, entries: list[WorkLogDraft]) -> list[WorkLogDraft]:
        self.entries.extend(entries)
        return entries

    def list_for_range(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[WorkLogDraft]:
        result = self.entries
        if start_date is not None:
            result = [entry for entry in result if entry.work_date >= start_date]
        if end_date is not None:
            result = [entry for entry in result if entry.work_date <= end_date]
        return list(result)


class WorkLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_from_draft(
        self,
        draft: WorkLogDraft,
        *,
        org_id: UUID,
        user_id: UUID,
        raw_message: RawInboundMessage | None = None,
        conversation_id: UUID | None = None,
    ) -> WorkLogEntry:
        entry = WorkLogEntry(
            conversation_id=conversation_id,
            org_id=org_id,
            user_id=user_id,
            raw_message_id=raw_message.id if raw_message else None,
            work_date=draft.work_date,
            start_time=draft.start_time,
            end_time=draft.end_time,
            timezone=draft.timezone,
            project=draft.project,
            site=draft.site,
            location_label=draft.location_label,
            location_address=draft.location_address,
            category=draft.category,
            title=draft.title,
            description=draft.description,
            summary=work_log_summary(draft),
            status=draft.status,
            confirmation_status=draft.confirmation_status,
            actions_taken_json=json.dumps(draft.actions_taken),
            participants_json=json.dumps(draft.participants),
            materials_used_json=json.dumps(draft.materials_used),
            equipment_json=json.dumps(draft.equipment),
            measurements_json=json.dumps(draft.measurements),
            blockers_json=json.dumps(draft.blockers),
            issues_json=json.dumps(draft.issues),
            safety_notes_json=json.dumps(draft.safety_notes),
            confidence=str(draft.confidence),
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def replace_conversation_drafts(
        self,
        *,
        conversation_id: UUID,
        org_id: UUID,
        user_id: UUID,
        drafts: list[WorkLogDraft],
        raw_message: RawInboundMessage | None = None,
    ) -> list[WorkLogEntry]:
        self.session.execute(
            delete(WorkLogEntry).where(
                WorkLogEntry.conversation_id == conversation_id,
                WorkLogEntry.confirmation_status == "draft",
            )
        )
        self.session.flush()
        return [
            self.add_from_draft(
                draft,
                org_id=org_id,
                user_id=user_id,
                raw_message=raw_message,
                conversation_id=conversation_id,
            )
            for draft in drafts
        ]

    def list_for_conversation(
        self,
        conversation_id: UUID,
        *,
        include_confirmed: bool = True,
    ) -> list[WorkLogEntry]:
        statement = select(WorkLogEntry).where(WorkLogEntry.conversation_id == conversation_id)
        if not include_confirmed:
            statement = statement.where(WorkLogEntry.confirmation_status == "draft")
        statement = statement.order_by(WorkLogEntry.work_date.asc(), WorkLogEntry.created_at.asc())
        return list(self.session.scalars(statement))

    def mark_conversation_drafts_confirmed(self, conversation_id: UUID) -> int:
        entries = self.list_for_conversation(conversation_id, include_confirmed=False)
        for entry in entries:
            entry.confirmation_status = "confirmed"
            self.session.add(entry)
        self.session.flush()
        return len(entries)

    def list_for_report(
        self,
        *,
        org_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        user_id: UUID | None = None,
    ) -> list[WorkLogEntry]:
        statement = select(WorkLogEntry).where(WorkLogEntry.org_id == org_id)
        if user_id is not None:
            statement = statement.where(WorkLogEntry.user_id == user_id)
        if start_date is not None:
            statement = statement.where(WorkLogEntry.work_date >= start_date)
        if end_date is not None:
            statement = statement.where(WorkLogEntry.work_date <= end_date)
        statement = statement.order_by(WorkLogEntry.work_date.asc(), WorkLogEntry.created_at.asc())
        return list(self.session.scalars(statement))


def work_log_summary(log: NormalizedWorkLog | WorkLogDraft) -> str:
    if isinstance(log, NormalizedWorkLog):
        return log.summary.strip()
    parts = [log.title.strip(), log.description.strip()]
    if log.participants:
        parts.append("Participants: " + "; ".join(log.participants))
    if log.actions_taken:
        parts.append("Actions: " + "; ".join(log.actions_taken))
    if log.materials_used:
        parts.append("Materials: " + "; ".join(log.materials_used))
    if log.equipment:
        parts.append("Equipment: " + "; ".join(log.equipment))
    if log.measurements:
        parts.append("Measurements: " + "; ".join(log.measurements))
    if log.blockers:
        parts.append("Blockers: " + "; ".join(log.blockers))
    return " ".join(part for part in parts if part).strip()


def work_log_from_db(entry: WorkLogEntry) -> WorkLogDraft:
    return WorkLogDraft(
        work_date=entry.work_date,
        start_time=entry.start_time,
        end_time=entry.end_time,
        timezone=entry.timezone or "Africa/Lagos",
        project=entry.project,
        site=entry.site,
        location_label=entry.location_label,
        location_address=entry.location_address,
        category=entry.category,
        title=entry.title or entry.summary[:80],
        description=entry.description or entry.summary,
        participants=json.loads(entry.participants_json or "[]"),
        actions_taken=json.loads(entry.actions_taken_json or "[]"),
        materials_used=json.loads(entry.materials_used_json or "[]"),
        equipment=json.loads(entry.equipment_json or "[]"),
        measurements=json.loads(entry.measurements_json or "[]"),
        issues=json.loads(entry.issues_json or "[]"),
        blockers=json.loads(entry.blockers_json or "[]"),
        safety_notes=json.loads(entry.safety_notes_json or "[]"),
        status=entry.status,  # type: ignore[arg-type]
        confirmation_status=entry.confirmation_status,  # type: ignore[arg-type]
        confidence=float(entry.confidence or 0),
    )


def _format_time_range(log: WorkLogDraft) -> str | None:
    if log.start_time and log.end_time:
        return f"{log.start_time.strftime('%H:%M')} to {log.end_time.strftime('%H:%M')}"
    if log.start_time:
        return f"from {log.start_time.strftime('%H:%M')}"
    if log.end_time:
        return f"until {log.end_time.strftime('%H:%M')}"
    return None


def _question_is_answered(question: str, logs: list[WorkLogDraft]) -> bool:
    text = question.lower()
    if any(token in text for token in ["who", "participant", "people", "accompanied"]):
        return any(log.participants for log in logs)
    if any(token in text for token in ["time", "start", "end", "hour"]):
        return any(log.start_time or log.end_time for log in logs)
    if any(token in text for token in ["site", "location", "where"]):
        return any(log.site or log.location_label or log.location_address for log in logs)
    if "project" in text:
        return any(log.project for log in logs)
    if any(token in text for token in ["material", "equipment", "tool"]):
        return any(log.materials_used or log.equipment for log in logs)
    if "safety" in text:
        return any(log.safety_notes for log in logs)
    if any(token in text for token in ["completed", "status", "planned"]):
        return any(log.status and log.status != "needs_review" for log in logs)
    return False


def build_confirmation_message(parse_result: ChatParseResult) -> str:
    if not parse_result.work_logs:
        if parse_result.report_request:
            request = parse_result.report_request
            title = request.title or f"{request.report_type.title()} report"
            return (
                f"I can prepare {title}. I will use the confirmed work logs "
                "for the selected period."
            )
        return parse_result.summary_for_user or (
            "I received this. Please send a little more detail so I can log it properly."
        )

    lines = ["I parsed this and saved it as a draft work log conversation:"]
    for index, log in enumerate(parse_result.work_logs, start=1):
        lines.append(f"{index}. {log.title}")
        lines.append(f"   Date: {log.work_date.isoformat()}")
        time_range = _format_time_range(log)
        if time_range:
            lines.append(f"   Time: {time_range}")
        if log.project:
            lines.append(f"   Project: {log.project}")
        if log.site or log.location_label or log.location_address:
            location_parts = [
                part for part in [log.site, log.location_label, log.location_address] if part
            ]
            lines.append("   Location: " + "; ".join(location_parts))
        if log.participants:
            lines.append("   People: " + "; ".join(log.participants))
        if log.actions_taken:
            lines.append("   Actions: " + "; ".join(log.actions_taken[:6]))
        if log.materials_used:
            lines.append("   Materials: " + "; ".join(log.materials_used[:6]))
        if log.equipment:
            lines.append("   Equipment: " + "; ".join(log.equipment[:6]))
        if log.measurements:
            lines.append("   Measurements: " + "; ".join(log.measurements[:6]))
        if log.safety_notes:
            lines.append("   Safety: " + "; ".join(log.safety_notes[:4]))
        if log.issues:
            lines.append("   Issues: " + "; ".join(log.issues[:4]))
        if log.blockers:
            lines.append("   Blockers: " + "; ".join(log.blockers[:3]))
        lines.append(f"   Status: {log.status}; confirmation: {log.confirmation_status}")

    questions = [
        question
        for question in parse_result.follow_up_questions
        if not _question_is_answered(question, parse_result.work_logs)
    ]
    if questions:
        lines.append("")
        lines.append("A few quick checks, only these details still look missing or uncertain:")
        lines.extend(f"{index}. {question}" for index, question in enumerate(questions, start=1))
    else:
        lines.append("")
        lines.append(
            "Reply confirm if this is correct, send more details to update this same conversation, "
            "or send new to start a fresh work-log conversation."
        )
    return "\n".join(lines)


def build_upload_processed_message(
    *,
    filename: str | None,
    parse_result: ChatParseResult,
) -> str:
    name = filename or "the upload"
    base = f"I uploaded and parsed {name}."
    confirmation = build_confirmation_message(parse_result)
    return f"{base}\n\n{confirmation}"
