from pydantic import BaseModel, Field


class NormalizedWorkLog(BaseModel):
    summary: str
    project: str | None = None
    site: str | None = None
    tasks: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
