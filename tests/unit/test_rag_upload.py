import httpx
import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.rag.schemas import RagDocument
from whatsapp_ai_agent.rag.upload import knowledge_upload_reply, upload_knowledge_document


@pytest.mark.asyncio
async def test_upload_knowledge_document_stores_file_and_posts_to_ai_search(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"success": True, "result": {"id": "item-1", "status": "queued"}},
        )

    settings = Settings(
        local_storage_dir=str(tmp_path),
        media_storage_backend="local",
        cloudflare_account_id="account-1",
        cloudflare_api_token="token-1",
        cloudflare_ai_search_instance="doceebot-rag",
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        from whatsapp_ai_agent.rag.cloudflare_client import CloudflareAIClient

        cf = CloudflareAIClient(settings=settings, http_client=http_client)
        uploaded = await upload_knowledge_document(
            RagDocument(
                org_id="org-1",
                source_type="company_document",
                visibility="worker_visible",
                text="Safety boots are required in the inverter room.",
                owner_user_id="user-1",
            ),
            filename="safety-policy.txt",
            settings=settings,
            cloudflare_client=cf,
        )

    assert uploaded.stored.backend == "local"
    assert uploaded.stored.local_path is not None
    assert uploaded.stored.local_path.read_text() == (
        "Safety boots are required in the inverter room."
    )
    assert (
        requests[0].url.path
        == "/client/v4/accounts/account-1/ai-search/instances/doceebot-rag/items"
    )
    assert b"org_id" in requests[0].content
    assert "queued" in knowledge_upload_reply(uploaded)
