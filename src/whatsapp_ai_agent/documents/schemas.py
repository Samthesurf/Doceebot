from pydantic import BaseModel, Field


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
