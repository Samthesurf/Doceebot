"""Preview how to unify Seyi/Nasir/Destiny onto WhatsApp (read-only).

For each Telegram-only user, checks whether a separate WhatsApp-only user row
already exists for the target phone. If none exists, the safe action is to set
the phone_number on the existing Telegram row (no merge). If a separate row
exists, a merge is required instead.
"""

from whatsapp_ai_agent.config import get_settings
from whatsapp_ai_agent.db.session import get_session_factory
from whatsapp_ai_agent.db.users_repository import (
    find_telegram_only_users,
    find_users_sharing_identifier,
)

TARGETS = {
    "7994559684": "+2347077410494",  # Seyi
    "7980843861": "+2349153002715",  # Nasir
    "5303133234": "+2348122792542",  # Destiny
}


def main() -> None:
    settings = get_settings()
    with get_session_factory(settings)() as s:
        tg_only = {u.telegram_user_id: u for u in find_telegram_only_users(s)}
        print("=== UNIFICATION PREVIEW (no writes) ===\n")
        for tg_id, wa_phone in TARGETS.items():
            user = tg_only.get(tg_id)
            if user is None:
                print(f"!! Telegram user {tg_id} not found among Telegram-only users\n")
                continue
            matches = find_users_sharing_identifier(s, phone_number=wa_phone)
            wa_rows = [m for m in matches if m.id != user.id]
            print(f"{user.display_name} (tg={tg_id})")
            print(f"    existing phone on row : {user.phone_number}")
            print(f"    target WA phone       : {wa_phone}")
            if wa_rows:
                for r in wa_rows:
                    msg = (
                        f"    !! separate WA row exists: "
                        f"id={r.id} tg={r.telegram_user_id} phone={r.phone_number}"
                    )
                    print(msg)
                print("    -> ACTION: MERGE separate WA row into this Telegram row\n")
            else:
                print(f"    -> ACTION: SET phone_number={wa_phone} on this row (no merge)\n")


if __name__ == "__main__":
    main()
