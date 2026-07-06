import asyncio
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.documents.schemas import ReportSpec
from whatsapp_ai_agent.llm.prompts import (
    CHAT_PARSE_SYSTEM_PROMPT,
    REPORT_SPEC_SYSTEM_PROMPT,
    chat_parse_user_prompt,
    report_spec_user_prompt,
)
from whatsapp_ai_agent.llm.schemas import (
    ChatParseResult,
    MediaExtraction,
    ReportRequest,
    WorkLogDraft,
)
from whatsapp_ai_agent.llm.structured_output import validate_model_text

T = TypeVar("T", bound=BaseModel)


class DeepSeekClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        self._owns_client = http_client is None
        self.http = http_client or httpx.AsyncClient(
            base_url=self.settings.deepseek_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
            timeout=60,
        )
        self.http.headers.setdefault(
            "Authorization",
            f"Bearer {self.settings.deepseek_api_key}",
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.http.aclose()

    async def __aenter__(self) -> "DeepSeekClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        temperature: float = 0.1,
    ) -> T:
        body: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        response: httpx.Response | None = None
        transient_statuses = {429, 500, 502, 503, 504}
        for attempt in range(3):
            response = await self.http.post("/chat/completions", json=body)
            if response.status_code == 400:
                fallback = dict(body)
                fallback.pop("response_format", None)
                response = await self.http.post("/chat/completions", json=fallback)
            if response.status_code not in transient_statuses or attempt == 2:
                break
            await asyncio.sleep(2**attempt)
        if response is None:
            raise RuntimeError("DeepSeek request did not return a response")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"DeepSeek request failed with HTTP {exc.response.status_code}"
            ) from exc

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("DeepSeek returned an unexpected response shape") from exc
        if not isinstance(content, str):
            raise RuntimeError("DeepSeek returned non-text content")
        return validate_model_text(schema, content)

    async def parse_chat_event(
        self,
        event: InboundEvent,
        *,
        media_extractions: list[MediaExtraction] | None = None,
        conversation_context: object | None = None,
    ) -> ChatParseResult:
        return await self._chat_completion_json(
            system_prompt=CHAT_PARSE_SYSTEM_PROMPT,
            user_prompt=chat_parse_user_prompt(
                event,
                media_extractions=media_extractions,
                conversation_context=conversation_context,
            ),
            schema=ChatParseResult,
        )

    async def build_report_spec(
        self,
        work_logs: list[WorkLogDraft],
        *,
        request: ReportRequest | None = None,
    ) -> ReportSpec:
        return await self._chat_completion_json(
            system_prompt=REPORT_SPEC_SYSTEM_PROMPT,
            user_prompt=report_spec_user_prompt(work_logs, request),
            schema=ReportSpec,
        )
