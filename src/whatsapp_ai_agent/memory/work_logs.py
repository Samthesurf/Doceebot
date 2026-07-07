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

    def mark_conversation_drafts_confirmed(
        self,
        conversation_id: UUID,
        indexes: list[int] | None = None,
    ) -> int:
        entries = self._select_indexed_drafts(conversation_id, indexes)
        for entry in entries:
            entry.confirmation_status = "confirmed"
            entry.status = "done" if entry.status == "draft" else entry.status
            self.session.add(entry)
        self.session.flush()
        return len(entries)

    def delete_conversation_drafts(
        self,
        conversation_id: UUID,
        indexes: list[int],
    ) -> int:
        entries = self._select_indexed_drafts(conversation_id, indexes)
        for entry in entries:
            self.session.delete(entry)
        self.session.flush()
        return len(entries)

    def cancel_conversation_drafts(self, conversation_id: UUID) -> int:
        entries = self.list_for_conversation(conversation_id, include_confirmed=False)
        for entry in entries:
            entry.status = "cancelled"
            entry.confirmation_status = "cancelled"
            self.session.add(entry)
        self.session.flush()
        return len(entries)

    def restore_conversation_drafts(
        self,
        *,
        conversation_id: UUID,
        org_id: UUID,
        user_id: UUID,
        drafts: list[WorkLogDraft],
        raw_message: RawInboundMessage | None = None,
    ) -> list[WorkLogEntry]:
        return self.replace_conversation_drafts(
            conversation_id=conversation_id,
            org_id=org_id,
            user_id=user_id,
            drafts=drafts,
            raw_message=raw_message,
        )

    def merge_conversation_drafts(
        self,
        conversation_id: UUID,
        indexes: list[int],
    ) -> WorkLogEntry | None:
        entries = self._select_indexed_drafts(conversation_id, indexes)
        if len(entries) < 2:
            return None
        keeper = entries[0]
        for entry in entries[1:]:
            keeper.title = _merge_text(keeper.title, entry.title, separator=" / ")[:255]
            keeper.description = _merge_text(keeper.description, entry.description)
            keeper.summary = _merge_text(keeper.summary, entry.summary)
            keeper.project = keeper.project or entry.project
            keeper.site = keeper.site or entry.site
            keeper.location_label = keeper.location_label or entry.location_label
            keeper.location_address = keeper.location_address or entry.location_address
            keeper.category = keeper.category or entry.category
            keeper.start_time = min(
                [value for value in [keeper.start_time, entry.start_time] if value],
                default=None,
            )
            keeper.end_time = max(
                [value for value in [keeper.end_time, entry.end_time] if value],
                default=None,
            )
            keeper.actions_taken_json = json.dumps(
                _merge_json_lists(keeper.actions_taken_json, entry.actions_taken_json)
            )
            keeper.participants_json = json.dumps(
                _merge_json_lists(keeper.participants_json, entry.participants_json)
            )
            keeper.materials_used_json = json.dumps(
                _merge_json_lists(keeper.materials_used_json, entry.materials_used_json)
            )
            keeper.equipment_json = json.dumps(
                _merge_json_lists(keeper.equipment_json, entry.equipment_json)
            )
            keeper.measurements_json = json.dumps(
                _merge_json_lists(keeper.measurements_json, entry.measurements_json)
            )
            keeper.blockers_json = json.dumps(
                _merge_json_lists(keeper.blockers_json, entry.blockers_json)
            )
            keeper.issues_json = json.dumps(
                _merge_json_lists(keeper.issues_json, entry.issues_json)
            )
            keeper.safety_notes_json = json.dumps(
                _merge_json_lists(keeper.safety_notes_json, entry.safety_notes_json)
            )
            self.session.delete(entry)
        self.session.add(keeper)
        self.session.flush()
        return keeper

    def _select_indexed_drafts(
        self,
        conversation_id: UUID,
        indexes: list[int] | None,
    ) -> list[WorkLogEntry]:
        entries = self.list_for_conversation(conversation_id, include_confirmed=False)
        if not indexes:
            return entries
        selected: list[WorkLogEntry] = []
        for index in indexes:
            if 1 <= index <= len(entries):
                selected.append(entries[index - 1])
        return selected

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


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _merge_json_lists(left: str | None, right: str | None) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [*_json_list(left), *_json_list(right)]:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


def _merge_text(left: str | None, right: str | None, *, separator: str = "\n") -> str:
    left_clean = (left or "").strip()
    right_clean = (right or "").strip()
    if not left_clean:
        return right_clean
    if not right_clean or right_clean == left_clean:
        return left_clean
    return f"{left_clean}{separator}{right_clean}"


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


def build_draft_board_message(
    drafts: list[WorkLogDraft],
    *,
    conversation_id: UUID | None = None,
) -> str:
    lines = ["Current work-log session drafts:"]
    if conversation_id:
        lines.append(f"Session: {conversation_id}")
    if not drafts:
        lines.append("No active draft logs yet.")
    for index, log in enumerate(drafts, start=1):
        lines.append("")
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
            lines.append("   People: " + "; ".join(log.participants[:6]))
        if log.materials_used:
            lines.append("   Materials: " + "; ".join(log.materials_used[:6]))
        lines.append(f"   Status: {log.status}; confirmation: {log.confirmation_status}")
    lines.append("")
    lines.append("Commands: confirm 1, confirm all, edit 1: ..., delete 1, merge 1 and 2,")
    lines.append("split 1: ..., undo, cancel, export, forget this session, search <query>,")
    lines.append("new, help, report this ...")
    return "\n".join(lines)


def build_help_message() -> str:
    return "\n".join(
        [
            "I am your work-log assistant, and I am happy to help you keep tidy records.",
            "Think of me as a colleague who never gets tired of writing things down.",
            "",
            "Here is what I can do for you:",
            "- Just send me a message about the work you did, and I will save it as a draft log.",
            "- Send photos, documents, or a voice note, and I will pull the work details from it.",
            "- status or show drafts: let you peek at the current draft board.",
            "- edit 1: <correction>: let you add more detail to a draft.",
            "- split 1: <how to split it>: break one long draft into separate logs.",
            "- merge 1 and 2: join drafts that belong to the same job.",
            "- delete 2: remove a draft you no longer need.",
            "- undo: bring back the previous draft board if something went wrong.",
            "- confirm 1 or confirm all: approve your drafts so they are locked in.",
            "- cancel: discard the active drafts and close the session.",
            "- new: start a fresh work-log conversation.",
            "- export: give you the current conversation id for audit export.",
            "- forget this session: remove this conversation's stored data.",
            "- search <query>: look back through past sessions, work logs, and messages.",
            "- report this <problem>: send this conversation and your note to the developer.",
            "",
            "I keep the conversation open and hold several draft logs at once, so you can "
            "build up a day's work step by step. Whenever you are ready, just tell me what "
            "you worked on.",
        ]
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
