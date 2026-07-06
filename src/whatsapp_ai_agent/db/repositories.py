import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.models import ManagedDocument, ManagedDocumentUpdate, RawInboundMessage
from whatsapp_ai_agent.media.storage import StoredObject


class RawInboundMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, message: RawInboundMessage) -> RawInboundMessage:
        self.session.add(message)
        self.session.flush()
        return message

    def add_event(
        self,
        event: InboundEvent,
        *,
        conversation_id: UUID | None = None,
    ) -> RawInboundMessage:
        message = RawInboundMessage(
            conversation_id=conversation_id,
            org_id=event.org_id,
            user_id=event.user_id,
            platform=event.platform,
            platform_message_id=event.platform_message_id,
            message_type=event.message_type,
            body_text=event.text,
            received_at=event.received_at,
            raw_payload_json=json.dumps(event.raw_payload, default=str),
        )
        return self.add(message)


class ManagedDocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_from_stored_object(
        self,
        *,
        org_id: UUID,
        stored: StoredObject,
        filename: str,
        document_kind: str,
        content_type: str | None = None,
        owner_user_id: UUID | None = None,
        display_name: str | None = None,
        source_type: str = "uploaded",
        status: str = "available",
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> ManagedDocument:
        document = ManagedDocument(
            org_id=org_id,
            owner_user_id=owner_user_id,
            display_name=display_name or filename,
            filename=filename,
            document_kind=document_kind,
            content_type=content_type or stored.content_type,
            storage_backend=stored.backend,
            storage_key=stored.key,
            storage_url=stored.url,
            local_path=str(stored.local_path) if stored.local_path else None,
            size_bytes=stored.size_bytes,
            sha256_hex=stored.sha256_hex,
            source_type=source_type,
            status=status,
            summary=summary,
            tags_json=json.dumps(tags or []),
        )
        self.session.add(document)
        self.session.flush()
        return document

    def update_storage_info(
        self,
        document: ManagedDocument,
        stored: StoredObject,
        *,
        status: str = "available",
    ) -> ManagedDocument:
        document.storage_backend = stored.backend
        document.storage_key = stored.key
        document.storage_url = stored.url
        document.local_path = str(stored.local_path) if stored.local_path else None
        document.size_bytes = stored.size_bytes
        document.sha256_hex = stored.sha256_hex
        document.content_type = stored.content_type or document.content_type
        document.status = status
        self.session.add(document)
        self.session.flush()
        return document

    def get(self, *, org_id: UUID, document_id: UUID) -> ManagedDocument | None:
        statement = select(ManagedDocument).where(
            ManagedDocument.org_id == org_id,
            ManagedDocument.id == document_id,
        )
        return self.session.scalar(statement)

    def list_documents(
        self,
        *,
        org_id: UUID,
        query: str | None = None,
        document_kind: str | None = None,
        source_type: str | None = None,
        limit: int = 50,
    ) -> list[ManagedDocument]:
        statement = select(ManagedDocument).where(ManagedDocument.org_id == org_id)
        if document_kind:
            statement = statement.where(ManagedDocument.document_kind == document_kind)
        if source_type:
            statement = statement.where(ManagedDocument.source_type == source_type)
        statement = statement.order_by(ManagedDocument.updated_at.desc()).limit(limit)
        documents = list(self.session.scalars(statement))
        if query:
            documents = _rank_documents(documents, query)
        return documents[:limit]

    def find_best_match(
        self,
        *,
        org_id: UUID,
        query: str | None = None,
        document_kinds: set[str] | None = None,
    ) -> ManagedDocument | None:
        statement = select(ManagedDocument).where(
            ManagedDocument.org_id == org_id,
            ManagedDocument.status.in_(["available", "pending_download"]),
        )
        if document_kinds:
            statement = statement.where(ManagedDocument.document_kind.in_(sorted(document_kinds)))
        statement = statement.order_by(ManagedDocument.updated_at.desc()).limit(100)
        documents = list(self.session.scalars(statement))
        if not documents:
            return None
        if query:
            ranked = _rank_documents(documents, query)
            return ranked[0] if ranked else None
        return documents[0]

    def add_update_record(
        self,
        *,
        org_id: UUID,
        document_id: UUID,
        instruction: str,
        changes: list[str],
        user_id: UUID | None = None,
        raw_message_id: UUID | None = None,
        update_kind: str = "table_upsert",
    ) -> ManagedDocumentUpdate:
        update = ManagedDocumentUpdate(
            org_id=org_id,
            document_id=document_id,
            user_id=user_id,
            raw_message_id=raw_message_id,
            update_kind=update_kind,
            instruction=instruction,
            changes_json=json.dumps(changes),
        )
        self.session.add(update)
        self.session.flush()
        return update


def _rank_documents(documents: list[ManagedDocument], query: str) -> list[ManagedDocument]:
    terms = {term for term in query.lower().replace("_", " ").split() if term}
    if not terms:
        return documents

    def score(document: ManagedDocument) -> int:
        haystack = " ".join(
            part
            for part in [
                document.display_name,
                document.filename,
                document.summary or "",
                document.tags_json or "",
                document.document_kind,
                document.source_type,
            ]
            if part
        ).lower()
        return sum(3 if term in haystack else 0 for term in terms) + sum(
            1 for term in terms if any(piece.startswith(term) for piece in haystack.split())
        )

    ranked = sorted(documents, key=lambda document: score(document), reverse=True)
    return [document for document in ranked if score(document) > 0] or documents
