from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from whatsapp_ai_agent.documents.schemas import DocumentTableUpdateRequest


class MediaExtraction(BaseModel):
    extracted_text: str = ""
    detected_language: str | None = None
    media_kind: Literal["voice", "audio", "image", "document", "text"] = "text"
    notable_details: list[str] = Field(default_factory=list)
    uncertain_parts: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class WorkLogDraft(BaseModel):
    work_date: date
    start_time: time | None = None
    end_time: time | None = None
    timezone: str = "Africa/Lagos"
    project: str | None = None
    site: str | None = None
    location_label: str | None = None
    location_address: str | None = None
    category: str | None = None
    participants: list[str] = Field(default_factory=list)
    title: str
    description: str
    actions_taken: list[str] = Field(default_factory=list)
    materials_used: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    measurements: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    status: Literal["planned", "in_progress", "done", "blocked", "needs_review"] = "done"
    confirmation_status: Literal["draft", "confirmed", "corrected"] = "draft"
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_event_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("title", "description")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator(
        "actions_taken",
        "participants",
        "materials_used",
        "equipment",
        "measurements",
        "issues",
        "blockers",
        "safety_notes",
        mode="before",
    )
    @classmethod
    def coerce_string_list(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class ReportRequest(BaseModel):
    report_type: Literal["daily", "weekly", "custom"] = "daily"
    title: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    output_format: Literal["docx", "xlsx", "both"] = "docx"
    requested_sections: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class ChatParseResult(BaseModel):
    intent: Literal[
        "work_log",
        "report_request",
        "knowledge_upload",
        "document_update",
        "correction",
        "other",
    ] = "work_log"
    work_logs: list[WorkLogDraft] = Field(default_factory=list)
    report_request: ReportRequest | None = None
    document_update_request: DocumentTableUpdateRequest | None = None
    summary_for_user: str = ""
    follow_up_questions: list[str] = Field(default_factory=list)
    needs_user_confirmation: bool = True
    confidence: float = Field(default=0.0, ge=0, le=1)

    @field_validator("intent", mode="before")
    @classmethod
    def normalize_intent(cls, value: object) -> object:
        if value == "document_update_request":
            return "document_update"
        return value

    @field_validator("follow_up_questions", mode="before")
    @classmethod
    def coerce_questions(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class NormalizedWorkLog(BaseModel):
    summary: str
    project: str | None = None
    site: str | None = None
    tasks: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
