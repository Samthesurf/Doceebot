from pydantic import BaseModel, Field


class SiteCandidate(BaseModel):
    site_id: str | None = None
    name: str
    confidence: float = Field(ge=0, le=1)
