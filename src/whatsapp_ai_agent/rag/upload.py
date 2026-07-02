from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.media.storage import StoredObject, get_media_storage
from whatsapp_ai_agent.rag.cloudflare_client import CloudflareAIClient
from whatsapp_ai_agent.rag.indexing import build_org_r2_key, prepare_text_item
from whatsapp_ai_agent.rag.retrieval import instance_id_for_org
from whatsapp_ai_agent.rag.schemas import RagDocument


@dataclass(frozen=True)
class UploadedKnowledgeDocument:
    document_id: str
    stored: StoredObject
    ai_search_item: dict


async def upload_knowledge_document(
    document: RagDocument,
    *,
    filename: str | None = None,
    settings: Settings | None = None,
    cloudflare_client: CloudflareAIClient | None = None,
) -> UploadedKnowledgeDocument:
    """Store approved knowledge in R2 and upload it to Cloudflare AI Search."""

    settings = settings or get_settings()
    data, metadata = prepare_text_item(document)
    document_id = metadata["document_id"]
    key = build_org_r2_key(document, filename=filename or f"{document_id}.txt")
    storage = get_media_storage(settings)
    if not hasattr(storage, "save_bytes"):
        raise RuntimeError("Configured media storage cannot save bytes")
    if settings.media_storage_backend == "r2":
        stored = storage.save_bytes(  # type: ignore[union-attr]
            key,
            data,
            content_type="text/plain; charset=utf-8",
            metadata=metadata,
        )
    else:
        stored = storage.save_bytes(  # type: ignore[union-attr]
            key,
            data,
            content_type="text/plain; charset=utf-8",
        )

    owns_client = cloudflare_client is None
    cloudflare_client = cloudflare_client or CloudflareAIClient(settings=settings)
    try:
        with NamedTemporaryFile("wb", suffix=".txt", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            ai_search_item = await cloudflare_client.upload_ai_search_item(
                instance_id_for_org(settings, document.org_id),
                tmp_path,
                namespace=settings.cloudflare_ai_search_namespace,
                item_name=Path(key).name,
                metadata=metadata,
            )
        finally:
            tmp_path.unlink(missing_ok=True)
    finally:
        if owns_client:
            await cloudflare_client.aclose()

    return UploadedKnowledgeDocument(
        document_id=document_id,
        stored=stored,
        ai_search_item=ai_search_item,
    )


def knowledge_upload_reply(uploaded: UploadedKnowledgeDocument) -> str:
    status = uploaded.ai_search_item.get("status") or "queued"
    return (
        "I uploaded that document to the organization knowledge base "
        "and queued it for search indexing.\n"
        f"Document ID: {uploaded.document_id}\n"
        f"Indexing status: {status}\n"
        "You can now ask questions about it once indexing finishes."
    )
