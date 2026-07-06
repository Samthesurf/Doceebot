#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import create_engine, text

from whatsapp_ai_agent.config import get_settings


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _row_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key, value in list(data.items()):
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat()
        else:
            data[key] = str(value) if value is not None and key.endswith("id") else value
    return data


def export_conversation(conversation_id: str | None) -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        if conversation_id is None:
            conversation = conn.execute(
                text(
                    """
                    SELECT *
                    FROM conversation_sessions
                    ORDER BY last_message_at DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
        else:
            conversation = conn.execute(
                text("SELECT * FROM conversation_sessions WHERE id = :id"),
                {"id": conversation_id},
            ).mappings().first()
        if conversation is None:
            raise SystemExit("conversation not found")

        cid = str(conversation["id"])
        turns = conn.execute(
            text(
                """
                SELECT *
                FROM conversation_turns
                WHERE conversation_id = :id
                ORDER BY occurred_at ASC, created_at ASC
                """
            ),
            {"id": cid},
        ).mappings().all()
        work_logs = conn.execute(
            text(
                """
                SELECT *
                FROM work_log_entries
                WHERE conversation_id = :id
                ORDER BY work_date ASC, created_at ASC
                """
            ),
            {"id": cid},
        ).mappings().all()
        audits = conn.execute(
            text(
                """
                SELECT id, raw_message_id, provider, model, purpose, input_json,
                       output_json, error_text, created_at
                FROM llm_audit_logs
                WHERE conversation_id = :id
                ORDER BY created_at ASC
                """
            ),
            {"id": cid},
        ).mappings().all()

    return {
        "conversation": _row_dict(conversation),
        "turns": [
            {
                **_row_dict(turn),
                "media": _json_loads(turn.get("media_json"), []),
                "raw_payload": _json_loads(turn.get("raw_payload_json"), {}),
                "metadata": _json_loads(turn.get("metadata_json"), {}),
            }
            for turn in turns
        ],
        "work_logs": [
            {
                **_row_dict(log),
                "participants": _json_loads(log.get("participants_json"), []),
                "actions_taken": _json_loads(log.get("actions_taken_json"), []),
                "materials_used": _json_loads(log.get("materials_used_json"), []),
                "equipment": _json_loads(log.get("equipment_json"), []),
                "measurements": _json_loads(log.get("measurements_json"), []),
                "issues": _json_loads(log.get("issues_json"), []),
                "blockers": _json_loads(log.get("blockers_json"), []),
                "safety_notes": _json_loads(log.get("safety_notes_json"), []),
            }
            for log in work_logs
        ],
        "llm_audits": [
            {
                **_row_dict(audit),
                "input": _json_loads(audit.get("input_json"), {}),
                "output": _json_loads(audit.get("output_json"), None),
            }
            for audit in audits
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a Doceebot conversation audit bundle.")
    parser.add_argument("conversation_id", nargs="?", help="Conversation UUID. Defaults to latest.")
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()
    print(
        json.dumps(
            export_conversation(args.conversation_id),
            ensure_ascii=False,
            indent=args.indent,
        )
    )


if __name__ == "__main__":
    main()
