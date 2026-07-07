import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
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
from whatsapp_ai_agent.integrations.telegram.sender import TelegramSender
from whatsapp_ai_agent.llm.deepseek_client import DeepSeekClient
from whatsapp_ai_agent.llm.gemini_client import GeminiMediaExtractor
from whatsapp_ai_agent.llm.schemas import ChatParseResult, MediaExtraction, WorkLogDraft
from whatsapp_ai_agent.media.downloader import (
    MediaDownloader,
    StoredInboundMedia,
    download_and_store_event_media,
    media_kind_from_content_type,
)
from whatsapp_ai_agent.memory.conversation_commands import (
    ConversationCommand,
    parse_conversation_command,
)
from whatsapp_ai_agent.memory.conversations import (
    ConversationContext,
    ConversationRepository,
    starts_new_conversation,
)
from whatsapp_ai_agent.memory.session_search import SessionSearcher
from whatsapp_ai_agent.memory.work_logs import (
    WorkLogRepository,
    build_confirmation_message,
    build_draft_board_message,
    build_help_message,
    build_upload_processed_message,
    work_log_from_db,
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
        conversation_context: ConversationContext | None = None,
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
    conversation_id: UUID | None = None
    work_logs: list[WorkLogDraft] = field(default_factory=list)
    generated_reports: list[GeneratedReportFile] = field(default_factory=list)
    document_results: list[DocumentAutomationResult] = field(default_factory=list)
    stored_media: list[StoredInboundMedia] = field(default_factory=list)


async def parse_inbound_event(
    event: InboundEvent,
    *,
    media_extractions: list[MediaExtraction] | None = None,
    normalizer: ChatNormalizer | None = None,
    conversation_context: ConversationContext | None = None,
) -> ChatParseResult:
    owns_normalizer = normalizer is None
    normalizer = normalizer or DeepSeekClient()
    try:
        if conversation_context is None:
            return await normalizer.parse_chat_event(event, media_extractions=media_extractions)
        try:
            return await normalizer.parse_chat_event(
                event,
                media_extractions=media_extractions,
                conversation_context=conversation_context,
            )
        except TypeError:
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
                        "Skipped Gemini media extraction because this MIME type is not supported."
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


def _result_for_reply(reply: str, conversation_id: UUID | None) -> ChatProcessingResult:
    return ChatProcessingResult(
        parse_result=ChatParseResult(intent="other", summary_for_user=reply, confidence=1.0),
        reply_text=reply,
        conversation_id=conversation_id,
    )


def _drafts_for_board(
    work_log_repo: WorkLogRepository,
    conversation_id: UUID,
) -> list[WorkLogDraft]:
    return [
        work_log_from_db(entry)
        for entry in work_log_repo.list_for_conversation(conversation_id, include_confirmed=False)
    ]


def _command_metadata(command: ConversationCommand) -> dict[str, object]:
    return {
        "command": command.name,
        "command_text": command.raw_text,
        "command_indexes": command.indexes,
    }


async def _send_developer_escalation_if_configured(
    *,
    settings: Settings,
    escalation_id: UUID,
    report_text: str,
    snapshot: dict[str, object],
) -> tuple[str, str | None, str | None]:
    destination = settings.developer_escalation_telegram_chat_id
    storage_dir = Path(settings.developer_escalation_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = storage_dir / f"{escalation_id}.json"
    bundle_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))

    if not destination:
        return "pending", "database", None
    if not settings.telegram_bot_token:
        return "failed", f"telegram:{destination}", "TELEGRAM_BOT_TOKEN is not configured"

    caption = (
        "Doceebot developer escalation\n"
        f"Escalation: {escalation_id}\n"
        f"User note: {report_text[:800] or 'No details supplied.'}"
    )
    try:
        sender = TelegramSender(settings=settings)
        await sender.send_document(chat_id=destination, path=bundle_path, caption=caption)
    except Exception as exc:
        logger.warning("Developer escalation delivery failed", exc_info=True)
        return "failed", f"telegram:{destination}", f"{type(exc).__name__}: {exc}"
    return "sent", f"telegram:{destination}", None


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
    conversation = None
    conversation_context: ConversationContext | None = None
    conversation_repo: ConversationRepository | None = None

    if db_session is not None:
        conversation_repo = ConversationRepository(db_session)
        conversation, _created = conversation_repo.get_or_create_for_event(
            scoped_event,
            force_new=starts_new_conversation(scoped_event),
        )
        work_log_repo = WorkLogRepository(db_session)
        command = parse_conversation_command(scoped_event)

        if starts_new_conversation(scoped_event):
            raw_message = RawInboundMessageRepository(db_session).add_event(
                scoped_event,
                conversation_id=conversation.id,
            )
            conversation_repo.log_inbound_event(
                conversation,
                scoped_event,
                raw_message=raw_message,
                metadata={"command": "new"},
            )
            reply = (
                "Started a new work-log conversation. Send the first update for this new "
                "set of work entries."
            )
            conversation_repo.log_outbound_reply(
                conversation,
                body_text=reply,
                platform=scoped_event.platform,
            )
            db_session.commit()
            return _result_for_reply(reply, conversation.id)

        if command is not None and command.should_short_circuit:
            raw_message = RawInboundMessageRepository(db_session).add_event(
                scoped_event,
                conversation_id=conversation.id,
            )
            conversation_repo.log_inbound_event(
                conversation,
                scoped_event,
                raw_message=raw_message,
                metadata=_command_metadata(command),
            )

            if command.name == "help":
                reply = build_help_message()
            elif command.name == "status":
                drafts = _drafts_for_board(work_log_repo, conversation.id)
                reply = build_draft_board_message(drafts, conversation_id=conversation.id)
            elif command.name == "confirm":
                confirmed_count = work_log_repo.mark_conversation_drafts_confirmed(
                    conversation.id,
                    indexes=command.indexes or None,
                )
                target = "selected" if command.indexes else "all"
                reply = f"Confirmed {confirmed_count} {target} draft work log(s)."
            elif command.name == "delete":
                if not command.indexes:
                    reply = "Tell me which draft to delete, for example: delete 2."
                else:
                    deleted_count = work_log_repo.delete_conversation_drafts(
                        conversation.id,
                        command.indexes,
                    )
                    drafts = _drafts_for_board(work_log_repo, conversation.id)
                    reply = (
                        f"Deleted {deleted_count} draft work log(s).\n\n"
                        + build_draft_board_message(drafts, conversation_id=conversation.id)
                    )
            elif command.name == "merge":
                if len(command.indexes) < 2:
                    reply = "Tell me at least two drafts to merge, for example: merge 1 and 2."
                else:
                    merged = work_log_repo.merge_conversation_drafts(
                        conversation.id,
                        command.indexes,
                    )
                    drafts = _drafts_for_board(work_log_repo, conversation.id)
                    reply = (
                        "Merged the selected drafts.\n\n"
                        + build_draft_board_message(drafts, conversation_id=conversation.id)
                        if merged
                        else "I could not find enough matching draft logs to merge."
                    )
            elif command.name == "undo":
                snapshot = conversation_repo.latest_previous_draft_snapshot(conversation.id)
                if not snapshot:
                    reply = "I do not have a previous draft board to restore yet."
                else:
                    work_log_repo.restore_conversation_drafts(
                        conversation_id=conversation.id,
                        org_id=resolved_org_id,
                        user_id=resolved_user_id,
                        drafts=snapshot,
                        raw_message=raw_message,
                    )
                    reply = "Restored the previous draft board.\n\n" + build_draft_board_message(
                        snapshot, conversation_id=conversation.id
                    )
            elif command.name == "cancel":
                cancelled_count = work_log_repo.cancel_conversation_drafts(conversation.id)
                conversation_repo.close_conversation(conversation, status="cancelled")
                reply = f"Cancelled this session and discarded {cancelled_count} draft log(s)."
            elif command.name == "export":
                snapshot = conversation_repo.export_payload(conversation.id)
                storage_settings = settings or get_settings()
                export_dir = Path(storage_settings.developer_escalation_storage_dir)
                export_dir.mkdir(parents=True, exist_ok=True)
                export_path = export_dir / f"conversation-{conversation.id}.json"
                export_path.write_text(
                    json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)
                )
                reply = (
                    f"Conversation export is ready. Session: {conversation.id}. "
                    f"Audit bundle saved for admin review as {export_path.name}."
                )
            elif command.name == "forget":
                forgotten_id = conversation.id
                conversation_repo.delete_conversation_data(conversation.id)
                db_session.commit()
                return _result_for_reply(
                    f"Deleted stored data for conversation {forgotten_id}.",
                    None,
                )
            elif command.name == "report":
                report_text = command.text or "No details supplied."
                snapshot = conversation_repo.export_payload(
                    conversation.id,
                    include_llm_payloads=False,
                    include_raw_payloads=False,
                )
                escalation = conversation_repo.create_developer_escalation(
                    conversation=conversation,
                    raw_message=raw_message,
                    report_text=report_text,
                    snapshot=snapshot,
                )
                (
                    delivery_status,
                    destination,
                    error_text,
                ) = await _send_developer_escalation_if_configured(
                    settings=settings or get_settings(),
                    escalation_id=escalation.id,
                    report_text=report_text,
                    snapshot=snapshot,
                )
                conversation_repo.update_developer_escalation_delivery(
                    escalation,
                    status=delivery_status,
                    destination=destination,
                    error_text=error_text,
                )
                reply = f"Reported this conversation to the developer. Report ID: {escalation.id}."
                if delivery_status == "pending":
                    reply += " It is saved in the developer escalation queue."
                elif delivery_status == "failed":
                    reply += " I saved it, but live delivery to the developer failed."
            elif command.name == "feedback":
                if command.text == "negative":
                    reply = (
                        "I marked the last response as wrong. Reply with edit 1: <correction>, "
                        "delete 1, undo, or report this <what went wrong>."
                    )
                else:
                    reply = "Thanks, I marked that feedback as positive."
            elif command.name == "search":
                search_query = command.text or command.raw_text
                searcher = SessionSearcher(db_session)
                results = searcher.search(
                    query=search_query,
                    org_id=resolved_org_id,
                    user_id=resolved_user_id,
                )
                if not results:
                    reply = "No past sessions found matching that query."
                else:
                    lines = [
                        f"Found {len(results)} past session(s) matching '{search_query}':",
                        "",
                    ]
                    for i, result in enumerate(results[:5], 1):
                        lines.append(
                            f"{i}. [{result.result_type}] "
                            f"{result.display_date}: {result.display_title}"
                        )
                        if result.snippet:
                            lines.append(f"   {result.snippet[:140]}")
                        if result.session_started_at:
                            lines.append(
                                f"   Session start: {result.session_started_at.isoformat()}"
                            )
                        lines.append(f"   Session ID: {result.session_id}")
                        lines.append("")
                    reply = "\n".join(lines)
            else:
                reply = build_help_message()

            conversation_repo.log_outbound_reply(
                conversation,
                body_text=reply,
                platform=scoped_event.platform,
                metadata={"command_response": command.name},
            )
            db_session.commit()
            return _result_for_reply(reply, conversation.id)

        previous_entries = work_log_repo.list_for_conversation(
            conversation.id,
            include_confirmed=False,
        )
        previous_logs = [work_log_from_db(entry) for entry in previous_entries]
        recent_turns = conversation_repo.recent_turn_payloads(conversation.id)
        if command is not None and not command.should_short_circuit:
            recent_turns.append(
                {
                    "direction": "system",
                    "message_type": "command_hint",
                    "body_text": command.raw_text,
                    "metadata": _command_metadata(command),
                }
            )

        # Cross-session retrieval: light search over past sessions for LLM context
        try:
            searcher = SessionSearcher(db_session)
            search_cross_results = searcher.search(
                query=scoped_event.text or "",
                org_id=resolved_org_id,
                user_id=resolved_user_id,
                limit=3,
            )
            if search_cross_results:
                context_lines = [
                    (
                        "Retrieved facts from earlier sessions. "
                        "Use these only as historical context, not as a replacement "
                        "for current-message facts."
                    ),
                    "",
                ]
                for result in search_cross_results:
                    snippet = result.snippet[:150] if result.snippet else ""
                    context_lines.append(
                        f"- [{result.result_type}] session {result.session_id}"
                        f" ({result.display_date}, status={result.session_status or 'unknown'}): "
                        f"{result.display_title}. {snippet}"
                    )
                recent_turns.append(
                    {
                        "direction": "system",
                        "message_type": "retrieved_context",
                        "body_text": "\n".join(context_lines),
                        "metadata": {"search_result_count": len(search_cross_results)},
                    }
                )
        except Exception:
            logger.warning("Cross-session search failed", exc_info=True)

        if previous_logs or recent_turns:
            conversation_context = ConversationContext(
                session_id=str(conversation.id),
                started_at=conversation.started_at.isoformat() if conversation.started_at else None,
                last_message_at=(
                    conversation.last_message_at.isoformat()
                    if conversation.last_message_at
                    else None
                ),
                previous_work_logs=previous_logs,
                recent_turns=recent_turns,
            )

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
        conversation_context=conversation_context,
    )

    raw_message = None
    document_results: list[DocumentAutomationResult] = []
    document_messages: list[str] = []
    if db_session is not None:
        raw_message = RawInboundMessageRepository(db_session).add_event(
            scoped_event,
            conversation_id=conversation.id if conversation else None,
        )
        if conversation_repo is not None and conversation is not None:
            inbound_metadata: dict[str, object] = {"stored_media_count": len(stored_media)}
            if conversation_context is not None:
                inbound_metadata["previous_drafts"] = [
                    log.model_dump(mode="json") for log in conversation_context.previous_work_logs
                ]
            parsed_command = parse_conversation_command(scoped_event)
            if parsed_command is not None:
                inbound_metadata.update(_command_metadata(parsed_command))
            conversation_repo.log_inbound_event(
                conversation,
                scoped_event,
                raw_message=raw_message,
                metadata=inbound_metadata,
            )
            if media_extractions is not None:
                conversation_repo.log_llm_audit(
                    conversation=conversation,
                    raw_message=raw_message,
                    provider="gemini",
                    model=(settings.gemini_model if settings is not None else "unknown"),
                    purpose="media_extraction",
                    input_payload={
                        "platform_message_id": scoped_event.platform_message_id,
                        "media": [item.media.model_dump(mode="json") for item in stored_media],
                    },
                    output_payload=[
                        extraction.model_dump(mode="json") for extraction in media_extractions
                    ],
                )
            conversation_repo.log_llm_audit(
                conversation=conversation,
                raw_message=raw_message,
                provider="deepseek",
                model=(settings.deepseek_model if settings is not None else "unknown"),
                purpose="chat_parse",
                input_payload={
                    "platform_message_id": scoped_event.platform_message_id,
                    "conversation_context_supplied": conversation_context is not None,
                },
                output_payload=parse_result.model_dump(mode="json"),
            )
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
        if conversation is not None:
            repo.replace_conversation_drafts(
                conversation_id=conversation.id,
                drafts=parse_result.work_logs,
                org_id=resolved_org_id,
                user_id=resolved_user_id,
                raw_message=raw_message,
            )
        else:
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
        if (
            not logs_for_report
            and db_session is not None
            and parse_result.report_request is not None
        ):
            report_request = parse_result.report_request
            retrieval_query = None
            if report_request.start_date is None and report_request.end_date is None:
                retrieval_query = scoped_event.text
            retrieved_entries = SessionSearcher(db_session).search_work_log_entries(
                query=retrieval_query,
                org_id=resolved_org_id,
                user_id=resolved_user_id,
                limit=50,
                confirmed_only=True,
                start_date=report_request.start_date,
                end_date=report_request.end_date,
            )
            logs_for_report = [work_log_from_db(entry) for entry in retrieved_entries]
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

    outbound_metadata: dict[str, object] = {}
    if scoped_event.media:
        filename = next((media.filename for media in scoped_event.media if media.filename), None)
        reply = build_upload_processed_message(filename=filename, parse_result=parse_result)
    else:
        reply = build_confirmation_message(parse_result)

    if (
        parse_result.intent == "other"
        and not parse_result.work_logs
        and parse_result.confidence < 0.5
    ):
        outbound_metadata["fallback"] = True
        reply = (
            "I may be misunderstanding this. Reply help to see commands, status to see "
            "current drafts, edit 1: <correction> to fix a draft, or report this <problem> "
            "to send the conversation to the developer."
        )

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

    if conversation_repo is not None and conversation is not None:
        conversation_repo.log_outbound_reply(
            conversation,
            body_text=reply,
            platform=scoped_event.platform,
            metadata=outbound_metadata or None,
        )

    return ChatProcessingResult(
        parse_result=parse_result,
        reply_text=reply,
        conversation_id=conversation.id if conversation is not None else None,
        work_logs=parse_result.work_logs,
        generated_reports=generated_reports,
        document_results=document_results,
        stored_media=stored_media,
    )
