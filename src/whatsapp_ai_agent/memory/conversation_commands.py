from __future__ import annotations

import re
from dataclasses import dataclass, field

from whatsapp_ai_agent.core.events import InboundEvent

_INDEX_RE = re.compile(r"\d+")
_REPORT_RE = re.compile(
    r"^report(?:\s+this)?(?:\s*[:\-]\s*|\s+)?(.*)$",
    re.IGNORECASE | re.DOTALL,
)
_EDIT_RE = re.compile(
    r"^(?:edit|update|fix)\s+(?:draft\s+|log\s+)?(\d+)\s*[:\-]?\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)
_DELETE_RE = re.compile(
    r"^(?:delete|remove|drop)\s+(?:draft\s+|log\s+)?(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_CONFIRM_RE = re.compile(r"^(?:confirm|confirmed|correct)(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)
_SPLIT_RE = re.compile(
    r"^split\s+(?:draft\s+|log\s+)?(\d+)(?:\s*[:\-]\s*(.*))?$",
    re.IGNORECASE | re.DOTALL,
)
_MERGE_RE = re.compile(r"^merge\s+(?:drafts?\s+|logs?\s+)?(.+)$", re.IGNORECASE | re.DOTALL)
_EXPORT_RE = re.compile(
    r"^(?:export|download)(?:\s+(?:this\s+)?(?:conversation|session))?$",
    re.IGNORECASE,
)
_FORGET_RE = re.compile(
    r"^(?:forget|delete)\s+(?:this\s+)?(?:conversation|session|chat)$",
    re.IGNORECASE,
)

_HELP_COMMANDS = {"help", "menu", "commands", "?"}
_STATUS_COMMANDS = {
    "status",
    "summary",
    "show",
    "show drafts",
    "drafts",
    "show logs",
    "current drafts",
    "what do you have",
}
_CANCEL_COMMANDS = {"cancel", "discard", "discard drafts", "cancel session", "discard session"}
_UNDO_COMMANDS = {"undo", "undo last", "rollback", "revert"}
_FEEDBACK_BAD = {"wrong", "not correct", "incorrect", "bad", "no wrong", "fix that"}
_FEEDBACK_GOOD = {"good", "looks good", "nice", "thanks", "thank you"}
_HANDOFF_COMMANDS = {
    "admin",
    "human",
    "talk to human",
    "talk to admin",
    "review this",
    "send to supervisor",
    "send to admin",
}


@dataclass(frozen=True)
class ConversationCommand:
    name: str
    raw_text: str
    text: str = ""
    indexes: list[int] = field(default_factory=list)
    should_short_circuit: bool = True


def normalize_command_text(text: str | None) -> str:
    return " ".join((text or "").strip().lower().split())


def _indexes(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(match.group(0)) for match in _INDEX_RE.finditer(value)]


def _is_all(value: str | None) -> bool:
    return normalize_command_text(value) in {"", "all", "drafts", "logs", "all drafts", "all logs"}


def parse_conversation_command(event: InboundEvent) -> ConversationCommand | None:
    if event.message_type != "text":
        return None
    raw = (event.text or "").strip()
    if not raw:
        return None
    normalized = normalize_command_text(raw)

    if normalized in _HELP_COMMANDS:
        return ConversationCommand(name="help", raw_text=raw)
    if normalized in _STATUS_COMMANDS:
        return ConversationCommand(name="status", raw_text=raw)
    if normalized in _UNDO_COMMANDS:
        return ConversationCommand(name="undo", raw_text=raw)
    if normalized in _CANCEL_COMMANDS:
        return ConversationCommand(name="cancel", raw_text=raw)
    if normalized in {"delete", "remove", "drop"}:
        return ConversationCommand(name="delete", raw_text=raw)
    if normalized == "merge":
        return ConversationCommand(name="merge", raw_text=raw)
    if normalized in _HANDOFF_COMMANDS:
        return ConversationCommand(
            name="report",
            raw_text=raw,
            text=f"User requested handoff: {raw}",
        )
    if normalized in _FEEDBACK_BAD:
        return ConversationCommand(name="feedback", raw_text=raw, text="negative")
    if normalized in _FEEDBACK_GOOD:
        return ConversationCommand(name="feedback", raw_text=raw, text="positive")
    if _EXPORT_RE.match(raw):
        return ConversationCommand(name="export", raw_text=raw)
    if _FORGET_RE.match(raw):
        return ConversationCommand(name="forget", raw_text=raw)

    report_match = _REPORT_RE.match(raw)
    report_command = (
        normalized == "report"
        or normalized.startswith("report this")
        or bool(re.match(r"^report\s*[:\-]", raw, re.IGNORECASE))
    )
    if report_match and report_command:
        report_text = (report_match.group(1) or "").strip()
        return ConversationCommand(name="report", raw_text=raw, text=report_text)

    confirm_match = _CONFIRM_RE.match(raw)
    if confirm_match:
        target_text = confirm_match.group(1)
        return ConversationCommand(
            name="confirm",
            raw_text=raw,
            indexes=[] if _is_all(target_text) else _indexes(target_text),
            text="all" if _is_all(target_text) else (target_text or ""),
        )

    delete_match = _DELETE_RE.match(raw)
    if delete_match:
        return ConversationCommand(
            name="delete",
            raw_text=raw,
            indexes=_indexes(delete_match.group(1)),
        )

    merge_match = _MERGE_RE.match(raw)
    if merge_match:
        return ConversationCommand(
            name="merge",
            raw_text=raw,
            indexes=_indexes(merge_match.group(1)),
        )

    edit_match = _EDIT_RE.match(raw)
    if edit_match:
        return ConversationCommand(
            name="ai_update",
            raw_text=raw,
            text=edit_match.group(2).strip(),
            indexes=[int(edit_match.group(1))],
            should_short_circuit=False,
        )

    split_match = _SPLIT_RE.match(raw)
    if split_match:
        return ConversationCommand(
            name="ai_update",
            raw_text=raw,
            text=(split_match.group(2) or "").strip(),
            indexes=[int(split_match.group(1))],
            should_short_circuit=False,
        )

    return None
