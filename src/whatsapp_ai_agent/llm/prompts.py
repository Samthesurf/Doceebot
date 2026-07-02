import json

from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.llm.schemas import MediaExtraction, ReportRequest, WorkLogDraft

NORMALIZE_WORK_LOG_SYSTEM_PROMPT = """
Return strict JSON matching the requested schema.
Do not invent dates, names, measurements, people, projects, or locations.
If a detail is missing, leave the field null or ask a follow-up question.
""".strip()

CHAT_PARSE_SYSTEM_PROMPT = """
You convert worker chat updates into strict JSON for an engineering work-log system.
Return one JSON object only, matching this shape:
{
  "intent": "work_log" | "report_request" | "knowledge_upload" |
    "document_update" | "correction" | "other",
  "work_logs": [
    {
      "work_date": "YYYY-MM-DD",
      "start_time": "HH:MM:SS" | null,
      "end_time": "HH:MM:SS" | null,
      "timezone": "Africa/Lagos",
      "project": string | null,
      "site": string | null,
      "location_label": string | null,
      "location_address": string | null,
      "category": string | null,
      "title": string,
      "description": string,
      "actions_taken": [string],
      "materials_used": [string],
      "equipment": [string],
      "measurements": [string],
      "issues": [string],
      "blockers": [string],
      "safety_notes": [string],
      "status": "planned" | "in_progress" | "done" | "blocked" | "needs_review",
      "confirmation_status": "draft",
      "confidence": number,
      "source_event_ids": [string],
      "evidence_refs": [string]
    }
  ],
  "report_request": null | {
    "report_type": "daily" | "weekly" | "custom",
    "title": string | null,
    "start_date": "YYYY-MM-DD" | null,
    "end_date": "YYYY-MM-DD" | null,
    "output_format": "docx" | "xlsx" | "both",
    "requested_sections": [string],
    "missing_fields": [string]
  },
  "document_update_request": null | {
    "instruction": string,
    "target_document": string | null,
    "document_kind": "xlsx" | "docx" | "csv" | "pdf" | "text" | "unknown",
    "sheet_name": string | null,
    "table_name": string | null,
    "key_columns": [string],
    "rows": [{"Column name": string | number | boolean | null}],
    "create_if_missing": boolean
  },
  "summary_for_user": string,
  "follow_up_questions": [string],
  "needs_user_confirmation": boolean,
  "confidence": number
}
Rules:
- Use the event local_date when the user says today or gives no date.
- Use yesterday only when the user explicitly says yesterday.
- Keep raw chat wording out of supervisor summaries, but preserve operational facts.
- Ask short useful follow-up questions for missing project, site, quantities,
  completion status, blockers, or safety issues.
- If the user requests a report, set intent to report_request and fill report_request.
- If the user asks to update, append to, create, or find an Excel file, workbook,
  spreadsheet, Word table, machine file, register, checklist, or logbook, set intent
  to document_update and fill document_update_request.
- If the user says to record, add, append, or update an entry in a named log,
  register, worksheet, table, or activity log, set intent to document_update even
  when the word Excel is omitted.
- For simple daily activity logs, prefer these exact column names when the user
  supplies the corresponding facts: Date, Start Time, End Time, Activity, People
  Participated, Site, Status, Notes.
- For document updates, put every concrete value the user supplied into rows. Use
  stable identifiers such as Machine, Equipment ID, Asset ID, Work Order No, Date,
  or Serial No as key_columns when available.
- If the user wants a new documentation file because no existing one is named, set
  create_if_missing to true and choose xlsx for registers/logs or docx for narrative
  Word table documents.
- If the user uploaded or described a company SOP, policy, manual, template,
  or knowledge document, set intent to knowledge_upload.
- Never use em dash or en dash characters in generated report-facing text.
""".strip()

MEDIA_EXTRACTION_PROMPT = """
Extract operational work-log information from this uploaded media.
Return JSON matching:
{
  "extracted_text": string,
  "detected_language": string | null,
  "media_kind": "voice" | "audio" | "image" | "document" | "text",
  "notable_details": [string],
  "uncertain_parts": [string],
  "confidence": number
}
Do not invent missing measurements, names, dates, or locations. If unsure, list uncertainty.
""".strip()

REPORT_SPEC_SYSTEM_PROMPT = """
You create strict JSON for a deterministic DOCX engineering report renderer.
Return one JSON object matching:
{
  "title": string,
  "sections": [
    {"heading": string, "paragraphs": [string]}
  ]
}
Rules:
- Ground every paragraph only in the supplied confirmed or draft work logs.
- Do not invent work, dates, workers, measurements, or sites.
- Use clear professional engineering English.
- Do not use em dash or en dash characters.
- If information is missing, state what is missing in a short section instead of guessing.
""".strip()


def event_context_payload(
    event: InboundEvent,
    *,
    media_extractions: list[MediaExtraction] | None = None,
) -> dict[str, object]:
    return {
        "platform": event.platform,
        "platform_message_id": event.platform_message_id,
        "message_type": event.message_type,
        "text": event.text,
        "local_date": event.local_date.isoformat(),
        "local_time": event.local_time.isoformat(),
        "timezone": event.timezone,
        "location": event.location.model_dump(mode="json") if event.location else None,
        "media": [media.model_dump(mode="json") for media in event.media],
        "media_extractions": [
            extraction.model_dump(mode="json") for extraction in media_extractions or []
        ],
    }


def chat_parse_user_prompt(
    event: InboundEvent,
    *,
    media_extractions: list[MediaExtraction] | None = None,
) -> str:
    payload = event_context_payload(event, media_extractions=media_extractions)
    return "Parse this inbound worker update into the required JSON.\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def report_spec_user_prompt(
    work_logs: list[WorkLogDraft],
    request: ReportRequest | None = None,
) -> str:
    payload = {
        "report_request": request.model_dump(mode="json") if request else None,
        "work_logs": [log.model_dump(mode="json") for log in work_logs],
    }
    return "Create the report JSON from these work logs.\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
