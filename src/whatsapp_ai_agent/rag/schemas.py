from pydantic import BaseModel, Field


class RagDocument(BaseModel):
    org_id: str
    source_type: str
    visibility: str
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)
