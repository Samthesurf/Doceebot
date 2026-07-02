import json

import httpx
import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.llm.deepseek_client import DeepSeekClient


@pytest.mark.asyncio
async def test_deepseek_parse_chat_event_posts_json_schema_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["headers"] = dict(request.headers)
        body = json.loads(request.content.decode())
        captured["body"] = body
        content = {
            "intent": "work_log",
            "work_logs": [
                {
                    "work_date": "2026-07-01",
                    "start_time": None,
                    "end_time": None,
                    "timezone": "Africa/Lagos",
                    "project": "Lekki inverter room",
                    "site": "Lekki branch",
                    "location_label": None,
                    "location_address": None,
                    "category": "electrical",
                    "title": "DB dressing",
                    "description": "The DB was dressed and continuity was tested.",
                    "actions_taken": ["Dressed DB", "Tested continuity"],
                    "materials_used": [],
                    "equipment": [],
                    "measurements": [],
                    "issues": [],
                    "blockers": [],
                    "safety_notes": [],
                    "status": "done",
                    "confirmation_status": "draft",
                    "confidence": 0.9,
                    "source_event_ids": ["chat-1"],
                    "evidence_refs": [],
                }
            ],
            "report_request": None,
            "summary_for_user": "Logged DB dressing.",
            "follow_up_questions": [],
            "needs_user_confirmation": True,
            "confidence": 0.9,
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )

    settings = Settings(
        deepseek_api_key="deepseek-test-key",
        deepseek_base_url="https://deepseek.test",
        deepseek_model="deepseek-test-model",
        _env_file=None,
    )
    async with httpx.AsyncClient(
        base_url="https://deepseek.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = DeepSeekClient(settings=settings, http_client=http_client)
        event = InboundEvent(
            platform="telegram",
            platform_message_id="chat-1",
            platform_user_id="user-1",
            platform_chat_id="chat",
            message_type="text",
            text="We dressed the DB today.",
            received_at="2026-07-01T10:00:00Z",
            local_date="2026-07-01",
            local_time="11:00:00",
            timezone="Africa/Lagos",
            raw_payload={},
        )
        parsed = await client.parse_chat_event(event)

    assert captured["path"] == "/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer deepseek-test-key"
    assert captured["body"]["model"] == "deepseek-test-model"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert parsed.work_logs[0].title == "DB dressing"
    assert parsed.work_logs[0].actions_taken == ["Dressed DB", "Tested continuity"]
