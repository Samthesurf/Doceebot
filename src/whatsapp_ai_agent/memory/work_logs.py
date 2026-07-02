import json
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import select
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
    ) -> WorkLogEntry:
        entry = WorkLogEntry(
            org_id=org_id,
            user_id=user_id,
            raw_message_id=raw_message.id if raw_message else None,
            work_date=draft.work_date,
            start_time=draft.start_time,
            end_time=draft.end_time,
            timezone=draft.timezone,
            project=draft.project,
            site=draft.site,
            title=draft.title,
            description=draft.description,
            summary=work_log_summary(draft),
            status=draft.status,
            confirmation_status=draft.confirmation_status,
            actions_taken_json=json.dumps(draft.actions_taken),
            materials_used_json=json.dumps(draft.materials_used),
            blockers_json=json.dumps(draft.blockers),
            issues_json=json.dumps(draft.issues),
            safety_notes_json=json.dumps(draft.safety_notes),
            confidence=str(draft.confidence),
        )
        self.session.add(entry)
        self.session.flush()
        return entry

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
    if log.actions_taken:
        parts.append("Actions: " + "; ".join(log.actions_taken))
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
        title=entry.title or entry.summary[:80],
        description=entry.description or entry.summary,
        actions_taken=json.loads(entry.actions_taken_json or "[]"),
        materials_used=json.loads(entry.materials_used_json or "[]"),
        issues=json.loads(entry.issues_json or "[]"),
        blockers=json.loads(entry.blockers_json or "[]"),
        safety_notes=json.loads(entry.safety_notes_json or "[]"),
        status=entry.status,  # type: ignore[arg-type]
        confirmation_status=entry.confirmation_status,  # type: ignore[arg-type]
        confidence=float(entry.confidence or 0),
    )


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

    lines = ["I parsed this and saved it as a draft work log:"]
    for index, log in enumerate(parse_result.work_logs, start=1):
        lines.append(f"{index}. {log.title}")
        lines.append(f"   Date: {log.work_date.isoformat()}")
        if log.project:
            lines.append(f"   Project: {log.project}")
        if log.site:
            lines.append(f"   Site: {log.site}")
        if log.actions_taken:
            lines.append("   Actions: " + "; ".join(log.actions_taken[:4]))
        if log.blockers:
            lines.append("   Blockers: " + "; ".join(log.blockers[:3]))

    questions = list(parse_result.follow_up_questions)
    if questions:
        lines.append("")
        lines.append("A few quick checks before I mark it confirmed:")
        lines.extend(f"{index}. {question}" for index, question in enumerate(questions, start=1))
    else:
        lines.append("")
        lines.append(
            "Reply confirm if this is correct, or send a correction like "
            "'change the site to Block D'."
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
