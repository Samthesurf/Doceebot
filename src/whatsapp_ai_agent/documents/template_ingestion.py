from pathlib import Path

from pydantic import BaseModel, Field


class TemplateProfile(BaseModel):
    path: str
    placeholders: list[str] = Field(default_factory=list)


def profile_template(path: Path) -> TemplateProfile:
    return TemplateProfile(path=str(path), placeholders=[])
