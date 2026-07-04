import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.repositories import ManagedDocumentRepository, RawInboundMessageRepository
from whatsapp_ai_agent.documents.automation import (
    apply_table_update_to_document,
    create_managed_table_document,
    register_generated_document_file,
    register_pending_inbound_media_document,
)
from whatsapp_ai_agent.documents.reports import GeneratedReportFile, generate_report_files
from whatsapp_ai_agent.documents.schemas import DocumentAutomationResult
from whatsapp_ai_agent.llm.deepseek_client import DeepSeekClient
from whatsapp_ai_agent.llm.gemini_client import GeminiMediaExtractor
from whatsapp_ai_agent.llm.schemas import ChatParseResult, MediaExtraction, WorkLogDraft
from whatsapp_ai_agent.media.downloader import (
    MediaDownloader,
    StoredInboundMedia,
    download_and_store_event_media,
    media_kind_from_content_type,
)
from whatsapp_ai_agent.memory.work_logs import (
    WorkLogRepository,
    build_confirmation_message,
    build_upload_processed_message,
)

logger = logging.getLogger(__name__)

_GENERIC_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream"}
_GEMINI_SUPPORTED_DOCUMENT_TYPES = {"application/pdf"}
_GEMINI_UNSUPPORTED_DOCUMENT_TYPES = {
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ChatNormalizer(Protocol):
    async def parse_chat_event(
        self,
        event: InboundEvent,
        *,
        media_extractions: list[MediaExtraction] | None = None,
    ) -> ChatParseResult: ...


class MediaExtractor(Protocol):
    async def extract_media(
        self,
        data: bytes,
        *,
        content_type: str,
        media_kind: str,
        filename: str | None = None,
        caption: str | None = None,
    ) -> MediaExtraction: ...


def _gemini_can_extract_content_type(content_type: str | None) -> bool:
    content = (content_type or "").lower()
    if not content or content in _GENERIC_CONTENT_TYPES:
        return False
    if content in _GEMINI_UNSUPPORTED_DOCUMENT_TYPES:
        return False
    if content in _GEMINI_SUPPORTED_DOCUMENT_TYPES:
        return True
    return content.startswith(("image/", "audio/", "text/"))


def _metadata_only_media_extraction(
    *,
    filename: str | None,
    content_type: str | None,
    media_kind: Literal["voice", "audio", "image", "document", "text"],
    reason: str,
) -> MediaExtraction:
    details = []
    if filename:
        details.append(f"Uploaded file: {filename}")
    if content_type:
        details.append(f"Content type: {content_type}")
    details.append(reason)
    return MediaExtraction(
        extracted_text="",
        media_kind=media_kind,
        notable_details=details,
        uncertain_parts=["Media content was not extracted automatically."],
        confidence=0.0,
    )


@dataclass(frozen=True)
class ChatProcessingResult:
    parse_result: ChatParseResult
    reply_text: str
    work_logs: list[WorkLogDraft] = field(default_factory=list)
    generated_reports: list[GeneratedReportFile] = field(default_factory=list)
    document_results: list[DocumentAutomationResult] = field(default_factory=list)
    stored_media: list[StoredInboundMedia] = field(default_factory=list)


async def parse_inbound_event(
    event: InboundEvent,
    *,
    media_extractions: list[MediaExtraction] | None = None,
    normalizer: ChatNormalizer | None = None,
) -> ChatParseResult:
    owns_normalizer = normalizer is None
    normalizer = normalizer or DeepSeekClient()
    try:
        return await normalizer.parse_chat_event(event, media_extractions=media_extractions)
    finally:
        if owns_normalizer and hasattr(normalizer, "aclose"):
            await normalizer.aclose()  # type: ignore[attr-defined]


async def extract_stored_media(
    event: InboundEvent,
    stored_media: list[StoredInboundMedia],
    *,
    settings: Settings | None = None,
    media_extractor: MediaExtractor | None = None,
) -> list[MediaExtraction]:
    if not stored_media:
        return []
    extractor = media_extractor or GeminiMediaExtractor(settings)
    extractions: list[MediaExtraction] = []
    for item in stored_media:
        content_type = item.media.content_type or "application/octet-stream"
        fallback_kind = (
            event.message_type
            if event.message_type in {"voice", "audio", "image", "document"}
            else "document"
        )
        media_kind = media_kind_from_content_type(content_type, fallback=fallback_kind)
        if not _gemini_can_extract_content_type(content_type):
            extractions.append(
                _metadata_only_media_extraction(
                    filename=item.media.filename,
                    content_type=content_type,
                    media_kind=media_kind,  # type: ignore[arg-type]
                    reason=(
                        "Skipped Gemini media extraction because this MIME type is not "
                        "supported."
                    ),
                )
            )
            continue
        try:
            extraction = await extractor.extract_media(
                item.data,
                content_type=content_type,
                media_kind=media_kind,
                filename=item.media.filename,
                caption=event.text,
            )
        except Exception as exc:
            logger.warning(
                "Media extraction failed for inbound upload filename=%s content_type=%s",
                item.media.filename,
                content_type,
                exc_info=True,
            )
            extraction = _metadata_only_media_extraction(
                filename=item.media.filename,
                content_type=content_type,
                media_kind=media_kind,  # type: ignore[arg-type]
                reason=f"Media extraction failed: {type(exc).__name__}.",
            )
        extractions.append(extraction)
    return extractions


async def process_inbound_event(
    event: InboundEvent,
    *,
    org_id: UUID | None = None,
    user_id: UUID | None = None,
    media_extractions: list[MediaExtraction] | None = None,
    normalizer: ChatNormalizer | None = None,
    db_session: Session | None = None,
    existing_work_logs: list[WorkLogDraft] | None = None,
    report_output_dir: Path | None = None,
    store_reports: bool = True,
    use_llm_for_reports: bool = True,
    settings: Settings | None = None,
    download_media: bool = False,
    extract_media: bool = False,
    media_downloader: MediaDownloader | None = None,
    media_extractor: MediaExtractor | None = None,
) -> ChatProcessingResult:
    resolved_org_id = org_id or event.org_id
    resolved_user_id = user_id or event.user_id
    if resolved_org_id is None or resolved_user_id is None:
        raise PermissionError("Event must have resolved org_id and user_id before AI processing")

    scoped_event = event.model_copy(update={"org_id": resolved_org_id, "user_id": resolved_user_id})
    stored_media: list[StoredInboundMedia] = []
    if download_media and scoped_event.media:
        scoped_event, stored_media = await download_and_store_event_media(
            scoped_event,
            settings=settings,
            downloader=media_downloader,
        )
        if extract_media and media_extractions is None:
            media_extractions = await extract_stored_media(
                scoped_event,
                stored_media,
                settings=settings,
                media_extractor=media_extractor,
            )

    parse_result = await parse_inbound_event(
        scoped_event,
        media_extractions=media_extractions,
        normalizer=normalizer,
    )

    raw_message = None
    document_results: list[DocumentAutomationResult] = []
    document_messages: list[str] = []
    if db_session is not None:
        raw_message = RawInboundMessageRepository(db_session).add_event(scoped_event)
        for media in scoped_event.media:
            registered_document = register_pending_inbound_media_document(
                event=scoped_event,
                media=media,
                db_session=db_session,
                org_id=resolved_org_id,
                owner_user_id=resolved_user_id,
            )
            if registered_document is not None:
                if registered_document.status == "available":
                    document_messages.append(
                        f"Stored {registered_document.filename} as an editable "
                        f"{registered_document.document_kind.upper()} document."
                    )
                else:
                    document_messages.append(
                        f"Registered {registered_document.filename}, but it is still "
                        f"{registered_document.status}."
                    )
        repo = WorkLogRepository(db_session)
        for draft in parse_result.work_logs:
            repo.add_from_draft(
                draft,
                org_id=resolved_org_id,
                user_id=resolved_user_id,
                raw_message=raw_message,
            )

        if parse_result.intent == "document_update" and parse_result.document_update_request:
            update_request = parse_result.document_update_request
            document_repo = ManagedDocumentRepository(db_session)
            query = update_request.target_document or update_request.instruction
            if update_request.document_kind in {"xlsx", "docx"}:
                kinds = {update_request.document_kind}
            else:
                kinds = {"xlsx", "docx"}
            document = document_repo.find_best_match(
                org_id=resolved_org_id,
                query=query,
                document_kinds=kinds,
            )
            try:
                if document and document.status == "available":
                    document_results.append(
                        apply_table_update_to_document(
                            document=document,
                            request=update_request,
                            db_session=db_session,
                            user_id=resolved_user_id,
                            raw_message=raw_message,
                            settings=settings,
                        )
                    )
                elif update_request.create_if_missing:
                    document_results.append(
                        create_managed_table_document(
                            org_id=resolved_org_id,
                            owner_user_id=resolved_user_id,
                            request=update_request,
                            db_session=db_session,
                            settings=settings,
                        )
                    )
                elif document and document.status != "available":
                    document_messages.append(
                        f"I found {document.filename}, but it is still {document.status}."
                    )
                else:
                    document_messages.append(
                        "I could not find a matching Excel or Word table document to update."
                    )
            except (RuntimeError, ValueError) as exc:
                document_messages.append(f"Document automation could not run: {exc}")
    elif parse_result.intent == "document_update":
        document_messages.append(
            "I understood this as a document update, but no database session was available."
        )

    generated_reports: list[GeneratedReportFile] = []
    if parse_result.intent == "report_request" and report_output_dir is not None:
        logs_for_report = existing_work_logs or parse_result.work_logs
        generated_reports = await generate_report_files(
            org_id=str(resolved_org_id),
            work_logs=logs_for_report,
            output_dir=report_output_dir,
            request=parse_result.report_request,
            store=store_reports,
            use_llm=use_llm_for_reports,
        )
        if db_session is not None:
            for report in generated_reports:
                register_generated_document_file(
                    org_id=resolved_org_id,
                    owner_user_id=resolved_user_id,
                    path=report.path,
                    stored=report.stored,
                    db_session=db_session,
                    summary="Generated from a report request.",
                    settings=settings,
                )

    if scoped_event.media:
        filename = next((media.filename for media in scoped_event.media if media.filename), None)
        reply = build_upload_processed_message(filename=filename, parse_result=parse_result)
    else:
        reply = build_confirmation_message(parse_result)

    if generated_reports:
        lines = [reply, "", "Generated report file(s):"]
        for report in generated_reports:
            if report.stored and report.stored.url:
                lines.append(f"- {report.format.upper()}: {report.stored.url}")
            else:
                lines.append(f"- {report.format.upper()}: {report.path.name}")
        reply = "\n".join(lines)

    if document_results or document_messages:
        lines = [reply, "", "Document automation:"]
        for result in document_results:
            lines.append(
                f"- {result.action.title()}: {result.document.filename} "
                f"({result.rows_applied} row(s))"
            )
            for change in result.changes[:5]:
                lines.append(f"  - {change}")
        lines.extend(f"- {message}" for message in document_messages)
        reply = "\n".join(lines)

    return ChatProcessingResult(
        parse_result=parse_result,
        reply_text=reply,
        work_logs=parse_result.work_logs,
        generated_reports=generated_reports,
        document_results=document_results,
        stored_media=stored_media,
    )
