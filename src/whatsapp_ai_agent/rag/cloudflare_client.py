import json
from pathlib import Path
from typing import Any

import httpx

from whatsapp_ai_agent.config import Settings, get_settings

DEFAULT_AI_SEARCH_METADATA_SCHEMA: list[dict[str, str]] = [
    {"field_name": "org_id", "data_type": "text"},
    {"field_name": "source_type", "data_type": "text"},
    {"field_name": "visibility", "data_type": "text"},
    {"field_name": "document_id", "data_type": "text"},
    {"field_name": "owner_user_id", "data_type": "text"},
]


class CloudflareAPIError(RuntimeError):
    """Safe Cloudflare API error that never includes credentials."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        errors: list[dict[str, Any]] | None = None,
        messages: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or []
        self.messages = messages or []


class CloudflareAIClient:
    """Small async client for the Cloudflare APIs used by Doceebot.

    It covers the control-plane operations the app needs now:
    R2 bucket discovery/creation, AI Search instance management, Items upload,
    and organization-scoped search calls. Object-level R2 uploads use the S3 API
    in ``media.storage.R2Storage`` because Cloudflare's REST API is for bucket
    management, not runtime object storage.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.cloudflare_account_id:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not configured")
        if not self.settings.cloudflare_api_token:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is not configured")

        self.base_url = self.settings.cloudflare_api_base_url.rstrip("/")
        self.account_id = self.settings.cloudflare_account_id
        self._owns_client = http_client is None
        self.http = http_client or httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.settings.cloudflare_api_token}"},
            timeout=60,
        )
        self.http.headers.setdefault(
            "Authorization",
            f"Bearer {self.settings.cloudflare_api_token}",
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.http.aclose()

    async def __aenter__(self) -> "CloudflareAIClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    def _account_path(self, path: str) -> str:
        return f"/accounts/{self.account_id}/{path.lstrip('/')}"

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self.http.request(method, self._url(path), **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise CloudflareAPIError(
                "Cloudflare returned a non-JSON response",
                status_code=response.status_code,
            ) from exc

        if response.status_code >= 400 or payload.get("success") is False:
            errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
            messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
            first_error = (
                errors[0].get("message") if errors and isinstance(errors[0], dict) else None
            )
            raise CloudflareAPIError(
                first_error or f"Cloudflare API request failed with HTTP {response.status_code}",
                status_code=response.status_code,
                errors=errors,
                messages=messages,
            )
        return payload

    async def list_r2_buckets(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", self._account_path("/r2/buckets"))
        result = payload.get("result")
        if isinstance(result, dict) and isinstance(result.get("buckets"), list):
            return result["buckets"]
        if isinstance(result, list):
            return result
        return []

    async def create_r2_bucket(self, name: str) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            self._account_path("/r2/buckets"),
            json={"name": name},
        )
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    async def ensure_r2_bucket(self, name: str) -> dict[str, Any]:
        for bucket in await self.list_r2_buckets():
            if bucket.get("name") == name:
                return bucket
        return await self.create_r2_bucket(name)

    async def list_ai_search_instances(
        self,
        *,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        if namespace:
            path = self._account_path(f"/ai-search/namespaces/{namespace}/instances")
        else:
            path = self._account_path("/ai-search/instances")
        payload = await self._request("GET", path)
        result = payload.get("result")
        return result if isinstance(result, list) else []

    async def create_ai_search_instance(
        self,
        instance_id: str,
        *,
        namespace: str | None = None,
        source_bucket: str | None = None,
        service_token_id: str | None = None,
        custom_metadata: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": instance_id,
            "embedding_model": self.settings.rag_embedding_model,
            "custom_metadata": custom_metadata or DEFAULT_AI_SEARCH_METADATA_SCHEMA,
        }
        if source_bucket:
            body.update({"type": "r2", "source": source_bucket})
            if service_token_id:
                body["token_id"] = service_token_id

        if namespace:
            path = self._account_path(f"/ai-search/namespaces/{namespace}/instances")
        else:
            path = self._account_path("/ai-search/instances")
        payload = await self._request("POST", path, json=body)
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    async def upload_ai_search_item(
        self,
        instance_id: str,
        file_path: Path,
        *,
        namespace: str | None = None,
        item_name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        path = self._ai_search_instance_path(instance_id, namespace=namespace, suffix="items")
        data = {"metadata": json.dumps(metadata)} if metadata else None
        with file_path.open("rb") as file_obj:
            files = {"file": (item_name or file_path.name, file_obj)}
            payload = await self._request("POST", path, files=files, data=data)
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    async def ai_search_stats(
        self,
        instance_id: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        path = self._ai_search_instance_path(instance_id, namespace=namespace, suffix="stats")
        payload = await self._request("GET", path)
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    async def search_ai_search_instance(
        self,
        instance_id: str,
        *,
        query: str,
        namespace: str | None = None,
        filters: dict[str, Any] | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        retrieval: dict[str, Any] = {}
        if filters:
            retrieval["filters"] = filters
        if max_results:
            retrieval["max_num_results"] = max_results

        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": query}],
        }
        if retrieval:
            body["ai_search_options"] = {"retrieval": retrieval}

        path = self._ai_search_instance_path(instance_id, namespace=namespace, suffix="search")
        payload = await self._request("POST", path, json=body)
        result = payload.get("result")
        if isinstance(result, dict) and isinstance(result.get("chunks"), list):
            return result["chunks"]
        return []

    def _ai_search_instance_path(
        self,
        instance_id: str,
        *,
        namespace: str | None = None,
        suffix: str,
    ) -> str:
        if namespace:
            return self._account_path(
                f"/ai-search/namespaces/{namespace}/instances/{instance_id}/{suffix}"
            )
        return self._account_path(f"/ai-search/instances/{instance_id}/{suffix}")
