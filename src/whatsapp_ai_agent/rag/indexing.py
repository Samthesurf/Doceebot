import re
from hashlib import sha256

from whatsapp_ai_agent.rag.schemas import MetadataValue, RagDocument

RAW_OR_INTERNAL_SOURCE_TYPES = {
    "raw_message",
    "raw_text",
    "raw_voice_note",
    "raw_image",
    "voice_note",
    "image",
    "transcript",
    "ocr_text",
    "ocr_artifact",
    "extracted_artifact",
    "inbound_event",
    "media_asset",
}

APPROVED_RAG_SOURCE_TYPES = {
    "company_document",
    "sop",
    "policy",
    "manual",
    "report_template",
    "template_note",
    "knowledge_snippet",
    "sanitized_work_log",
    "daily_summary",
    "weekly_summary",
    "org_summary",
    "approved_summary",
}

AI_SEARCH_METADATA_FIELDS = ("org_id", "source_type", "visibility", "document_id", "owner_user_id")
_SAFE_KEY_RE = re.compile(r"[^a-zA-Z0-9._=-]+")


def stable_document_id(document: RagDocument) -> str:
    if document.document_id:
        return document.document_id
    digest_source = "\n".join(
        [document.org_id, document.source_type, document.visibility, document.text]
    )
    digest = sha256(digest_source.encode()).hexdigest()
    return digest[:32]


def ensure_org_metadata(document: RagDocument) -> RagDocument:
    """Return a copy whose metadata repeats mandatory tenant fields.

    Cloudflare AI Search is not the security boundary, but every indexed item
    must still carry tenant metadata so queries can filter before retrieval and
    the backend can post-filter after retrieval.
    """

    if not document.org_id:
        raise ValueError("RAG document must include org_id")

    metadata: dict[str, MetadataValue] = dict(document.metadata)
    document_id = stable_document_id(document)
    metadata.update(
        {
            "org_id": document.org_id,
            "source_type": document.source_type,
            "visibility": document.visibility,
            "document_id": document_id,
        }
    )
    if document.owner_user_id:
        metadata["owner_user_id"] = document.owner_user_id
    return document.model_copy(update={"document_id": document_id, "metadata": metadata})


def assert_indexable(document: RagDocument) -> None:
    source_type = document.source_type.strip().lower()
    if source_type in RAW_OR_INTERNAL_SOURCE_TYPES:
        raise ValueError(f"{document.source_type!r} must not be indexed into supervisor-facing RAG")
    if source_type not in APPROVED_RAG_SOURCE_TYPES:
        raise ValueError(
            f"{document.source_type!r} is not an approved RAG source_type; sanitize it first"
        )
    if len(document.text.strip()) < 3:
        raise ValueError("RAG document text is too short to index")


def build_ai_search_metadata(document: RagDocument) -> dict[str, str]:
    """Build the five custom fields supported by the Doceebot AI Search schema."""

    document = ensure_org_metadata(document)
    metadata: dict[str, str] = {}
    for field in AI_SEARCH_METADATA_FIELDS:
        value = document.metadata.get(field)
        if value is None:
            continue
        metadata[field] = str(value)[:500]
    return metadata


def slug_key_part(value: str) -> str:
    value = value.strip().replace("/", " ").replace("\\", " ")
    value = _SAFE_KEY_RE.sub("-", value).strip(".-_")
    return value or "item"


def build_org_r2_key(document: RagDocument, *, filename: str | None = None) -> str:
    document = ensure_org_metadata(document)
    name = slug_key_part(filename or f"{document.document_id}.txt")
    source = slug_key_part(document.source_type)
    return f"orgs/{slug_key_part(document.org_id)}/rag/{source}/{name}"


def prepare_text_item(document: RagDocument) -> tuple[bytes, dict[str, str]]:
    assert_indexable(document)
    metadata = build_ai_search_metadata(document)
    return document.text.encode("utf-8"), metadata
