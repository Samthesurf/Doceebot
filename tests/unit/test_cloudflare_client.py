import json

import httpx
import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.rag.cloudflare_client import CloudflareAIClient, CloudflareAPIError


def _settings() -> Settings:
    return Settings(
        cloudflare_account_id="account-1",
        cloudflare_api_token="token-1",
        rag_embedding_model="@cf/baai/bge-base-en-v1.5",
        _env_file=None,
    )


@pytest.mark.asyncio
async def test_ensure_r2_bucket_creates_missing_bucket():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"success": True, "result": {"buckets": []}})
        body = json.loads(request.content.decode())
        assert body == {"name": "doceebot-storage"}
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {"name": "doceebot-storage", "creation_date": "2026-07-01T00:00:00Z"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = CloudflareAIClient(settings=_settings(), http_client=http_client)
        bucket = await client.ensure_r2_bucket("doceebot-storage")

    assert bucket["name"] == "doceebot-storage"
    assert requests[0].url.path == "/client/v4/accounts/account-1/r2/buckets"
    assert requests[1].method == "POST"
    assert requests[1].headers["authorization"] == "Bearer token-1"


@pytest.mark.asyncio
async def test_search_ai_search_instance_posts_filters_and_max_results():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "chunks": [
                        {
                            "text": "Safety policy chunk",
                            "item": {"metadata": {"org_id": "org-1"}},
                        }
                    ]
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = CloudflareAIClient(settings=_settings(), http_client=http_client)
        chunks = await client.search_ai_search_instance(
            "shared-doceebot",
            query="safety policy",
            filters={"org_id": "org-1", "visibility": "worker_visible"},
            max_results=5,
        )

    assert captured["path"] == (
        "/client/v4/accounts/account-1/ai-search/instances/shared-doceebot/search"
    )
    assert captured["body"] == {
        "messages": [{"role": "user", "content": "safety policy"}],
        "ai_search_options": {
            "retrieval": {
                "filters": {"org_id": "org-1", "visibility": "worker_visible"},
                "max_num_results": 5,
            }
        },
    }
    assert chunks[0]["text"] == "Safety policy chunk"


@pytest.mark.asyncio
async def test_cloudflare_api_error_is_safe_and_structured():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "success": False,
                "errors": [{"code": 10000, "message": "Authentication error"}],
                "messages": [],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = CloudflareAIClient(settings=_settings(), http_client=http_client)
        with pytest.raises(CloudflareAPIError) as exc_info:
            await client.list_ai_search_instances()

    exc = exc_info.value
    assert exc.status_code == 403
    assert "Authentication error" in str(exc)
    assert "token-1" not in str(exc)
