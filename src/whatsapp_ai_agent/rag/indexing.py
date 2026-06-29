from whatsapp_ai_agent.rag.schemas import RagDocument


def ensure_org_metadata(document: RagDocument) -> RagDocument:
    if not document.org_id:
        raise ValueError("RAG document must include org_id")
    return document
