"""Sync Seyi/Nasir/Destiny onto WhatsApp by attaching their number to the
existing Telegram User row (no merge needed; history stays intact).

Stores the FULL E.164 phone (e.g. +2347077410494) because the WhatsApp inbound
resolver (tenant_scope._phone_candidates) matches full numbers directly, and a
masked value would break resolution (the digit-fallback drops the masked chars).

Idempotent: only sets the phone when it is currently empty, and only when no
separate WhatsApp-only row already exists for that number.
"""

from whatsapp_ai_agent.config import get_settings
from whatsapp_ai_agent.db.models import User
from whatsapp_ai_agent.db.session import get_session_factory
from whatsapp_ai_agent.db.users_repository import (
    find_telegram_only_users,
    find_users_sharing_identifier,
)

# Telegram id -> full E.164 WhatsApp number
TARGETS = {
    "7994559684": "+2347077410494",  # Seyi
    "7980843861": "+2349153002715",  # Nasir
    "5303133234": "+2348122792542",  # Destiny
}


def _normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return f"+{digits}" if digits else value


def main() -> None:
    settings = get_settings()
    with get_session_factory(settings)() as s:
        tg_only = {u.telegram_user_id: u for u in find_telegram_only_users(s)}
        applied = []
        for tg_id, raw_phone in TARGETS.items():
            phone = _normalize_phone(raw_phone)
            user = tg_only.get(tg_id)
            if user is None:
                print(f"SKIP tg={tg_id}: not a Telegram-only user")
                continue
            # Refuse if a separate WA row already exists (would need a merge).
            wa_rows = [
                m
                for m in find_users_sharing_identifier(s, phone_number=phone)
                if m.id != user.id
            ]
            if wa_rows:
                print(f"SKIP {user.display_name}: separate WA row exists -> merge needed")
                continue
            if user.phone_number == phone:
                print(f"OK   {user.display_name}: phone already set to {phone}")
                continue
            if user.phone_number:
                print(
                    f"SKIP {user.display_name}: already has phone {user.phone_number} "
                    f"(expected empty for a Telegram-only row)"
                )
                continue
            user.phone_number = phone
            applied.append((user.display_name, phone, user.id))
            print(f"SET  {user.display_name}: phone_number -> {phone}")

        if applied:
            s.commit()
            print(f"\nCommitted {len(applied)} update(s).")
        else:
            print("\nNothing to change.")


if __name__ == "__main__":
    main()
