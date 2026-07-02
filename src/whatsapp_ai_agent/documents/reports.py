from dataclasses import dataclass
from datetime import date
from pathlib import Path

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.documents.docx_generator import generate_docx_report
from whatsapp_ai_agent.documents.schemas import ReportSection, ReportSpec, WorkbookRow, WorkbookSpec
from whatsapp_ai_agent.documents.xlsx_generator import generate_xlsx_workbook
from whatsapp_ai_agent.llm.deepseek_client import DeepSeekClient
from whatsapp_ai_agent.llm.schemas import ReportRequest, WorkLogDraft
from whatsapp_ai_agent.media.storage import StoredObject, get_media_storage, org_object_key


@dataclass(frozen=True)
class GeneratedReportFile:
    format: str
    path: Path
    stored: StoredObject | None = None


def deterministic_report_spec(
    work_logs: list[WorkLogDraft],
    *,
    request: ReportRequest | None = None,
) -> ReportSpec:
    if request and request.title:
        title = request.title
    elif work_logs:
        title = f"Work Report for {work_logs[0].work_date.isoformat()}"
    else:
        title = "Work Report"

    overview_parts: list[str] = []
    if work_logs:
        dates = sorted({log.work_date.isoformat() for log in work_logs})
        overview_parts.append(f"This report covers {len(work_logs)} logged work update(s).")
        overview_parts.append("Dates covered: " + ", ".join(dates) + ".")
    else:
        overview_parts.append("No work logs were available for the selected period.")

    sections = [ReportSection(heading="Overview", paragraphs=overview_parts)]
    for index, log in enumerate(work_logs, start=1):
        paragraphs = [log.description]
        details = []
        if log.project:
            details.append(f"Project: {log.project}")
        if log.site:
            details.append(f"Site: {log.site}")
        details.append(f"Status: {log.status}")
        if details:
            paragraphs.append("; ".join(details) + ".")
        if log.actions_taken:
            paragraphs.append("Actions taken: " + "; ".join(log.actions_taken) + ".")
        if log.materials_used:
            paragraphs.append("Materials used: " + "; ".join(log.materials_used) + ".")
        if log.issues:
            paragraphs.append("Issues noted: " + "; ".join(log.issues) + ".")
        if log.blockers:
            paragraphs.append("Blockers: " + "; ".join(log.blockers) + ".")
        if log.safety_notes:
            paragraphs.append("Safety notes: " + "; ".join(log.safety_notes) + ".")
        sections.append(ReportSection(heading=f"{index}. {log.title}", paragraphs=paragraphs))

    return ReportSpec(title=title, sections=sections)


async def build_report_spec(
    work_logs: list[WorkLogDraft],
    *,
    request: ReportRequest | None = None,
    use_llm: bool = True,
    deepseek_client: DeepSeekClient | None = None,
) -> ReportSpec:
    if not use_llm:
        return deterministic_report_spec(work_logs, request=request)
    owns_client = deepseek_client is None
    deepseek_client = deepseek_client or DeepSeekClient()
    try:
        return await deepseek_client.build_report_spec(work_logs, request=request)
    finally:
        if owns_client:
            await deepseek_client.aclose()


def workbook_spec_from_work_logs(
    work_logs: list[WorkLogDraft], *, title: str = "Work Logs"
) -> WorkbookSpec:
    return WorkbookSpec(
        title=title,
        rows=[
            WorkbookRow(
                date=log.work_date.isoformat(),
                worker="",
                project=log.project,
                summary=log.title + ": " + log.description,
            )
            for log in work_logs
        ],
    )


def _format_slug(value: str) -> str:
    return (
        "-".join(part for part in value.lower().replace("/", " ").split() if part)[:80] or "report"
    )


def store_generated_file(
    *,
    org_id: str,
    path: Path,
    content_type: str,
    settings: Settings | None = None,
) -> StoredObject:
    settings = settings or get_settings()
    storage = get_media_storage(settings)
    key = org_object_key(org_id, "generated", path.name)
    if hasattr(storage, "save_file"):
        return storage.save_file(  # type: ignore[union-attr]
            key,
            path,
            content_type=content_type,
            metadata={"org_id": org_id, "source_type": "generated_report"},
        )
    return storage.save_bytes(key, path.read_bytes(), content_type=content_type)


async def generate_report_files(
    *,
    org_id: str,
    work_logs: list[WorkLogDraft],
    output_dir: Path,
    request: ReportRequest | None = None,
    formats: set[str] | None = None,
    store: bool = True,
    use_llm: bool = True,
    settings: Settings | None = None,
    deepseek_client: DeepSeekClient | None = None,
) -> list[GeneratedReportFile]:
    settings = settings or get_settings()
    requested_formats = formats or {"docx"}
    if request and request.output_format == "both":
        requested_formats = {"docx", "xlsx"}
    elif request and request.output_format in {"docx", "xlsx"}:
        requested_formats = {request.output_format}

    spec = await build_report_spec(
        work_logs,
        request=request,
        use_llm=use_llm,
        deepseek_client=deepseek_client,
    )
    slug = _format_slug(spec.title)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[GeneratedReportFile] = []

    if "docx" in requested_formats:
        docx_path = generate_docx_report(spec, output_dir / f"{slug}.docx")
        stored = (
            store_generated_file(
                org_id=org_id,
                path=docx_path,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                settings=settings,
            )
            if store
            else None
        )
        generated.append(GeneratedReportFile(format="docx", path=docx_path, stored=stored))

    if "xlsx" in requested_formats:
        workbook = workbook_spec_from_work_logs(work_logs, title=slug[:31] or "Work Logs")
        xlsx_path = generate_xlsx_workbook(workbook, output_dir / f"{slug}.xlsx")
        stored = (
            store_generated_file(
                org_id=org_id,
                path=xlsx_path,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                settings=settings,
            )
            if store
            else None
        )
        generated.append(GeneratedReportFile(format="xlsx", path=xlsx_path, stored=stored))

    return generated


def date_range_for_request(request: ReportRequest | None, fallback_date: date) -> tuple[date, date]:
    if request and request.start_date and request.end_date:
        return request.start_date, request.end_date
    if request and request.start_date:
        return request.start_date, request.start_date
    return fallback_date, fallback_date
