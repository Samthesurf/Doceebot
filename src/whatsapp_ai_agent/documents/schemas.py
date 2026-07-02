from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ReportSection(BaseModel):
    heading: str
    paragraphs: list[str] = Field(default_factory=list)


class ReportSpec(BaseModel):
    title: str
    sections: list[ReportSection] = Field(default_factory=list)


class WorkbookRow(BaseModel):
    date: str
    worker: str
    project: str | None = None
    summary: str


class WorkbookSpec(BaseModel):
    title: str
    rows: list[WorkbookRow] = Field(default_factory=list)


DocumentKind = Literal["xlsx", "docx", "csv", "pdf", "text", "unknown"]
DocumentSourceType = Literal["uploaded", "generated", "updated", "chat_created"]


class DocumentTableUpdateRequest(BaseModel):
    """Structured request for updating a table-like business document."""

    instruction: str = ""
    target_document: str | None = None
    document_kind: DocumentKind = "unknown"
    sheet_name: str | None = None
    table_name: str | None = None
    key_columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    create_if_missing: bool = True

    @field_validator("key_columns", mode="before")
    @classmethod
    def coerce_key_columns(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("rows", mode="before")
    @classmethod
    def coerce_rows(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        return value


class ManagedDocumentSummary(BaseModel):
    id: str
    org_id: str
    filename: str
    display_name: str
    document_kind: DocumentKind
    source_type: str
    status: str
    content_type: str | None = None
    size_bytes: int | None = None
    sha256_hex: str | None = None
    storage_backend: str | None = None
    storage_key: str | None = None
    url: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class DocumentAutomationResult(BaseModel):
    document: ManagedDocumentSummary
    action: Literal["created", "updated", "registered"]
    changes: list[str] = Field(default_factory=list)
    rows_applied: int = 0


class DocumentationAutomationIdea(BaseModel):
    slug: str
    title: str
    formats: list[DocumentKind]
    chat_inputs: list[str]
    typical_fields: list[str]
    automation_notes: str
    source_notes: str | None = None
