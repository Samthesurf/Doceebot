from typing import Literal

from pydantic import BaseModel, Field, field_validator

from whatsapp_ai_agent.core.permissions import Role

MetadataValue = str | int | float | bool


class RagDocument(BaseModel):
    """A document or approved summary that may be indexed into Cloudflare AI Search."""

    org_id: str
    source_type: str
    visibility: str
    text: str
    document_id: str | None = None
    title: str | None = None
    owner_user_id: str | None = None
    allowed_roles: list[Role] = Field(default_factory=list)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @field_validator("org_id", "source_type", "visibility", "text")
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class RagSearchRequest(BaseModel):
    org_id: str
    query: str
    role: Role = Role.WORKER
    user_id: str | None = None
    source_types: list[str] | None = None
    visibilities: list[str] | None = None
    max_results: int = Field(default=8, ge=1, le=50)


class RagSearchResult(BaseModel):
    org_id: str
    document_id: str | None = None
    source_type: str | None = None
    visibility: str | None = None
    text: str
    score: float | None = None
    item_key: str | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class RetrievalRoute(str):
    SQL = "sql"
    RAG = "rag"
    HYBRID = "hybrid"


RagBackend = Literal["cloudflare_ai_search", "disabled"]
