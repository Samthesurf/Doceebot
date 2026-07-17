"""Preview (read-only) of Telegram-only users that could be unified onto WhatsApp.

This script does NOT mutate any data. It lists every user that has a Telegram id
but no WhatsApp phone (i.e. people who texted on Telegram and now have history
there), and for each reports whether a separate WhatsApp-only user row also exists
(a split account) so an admin merge can fold the two together.

Run:
    uv run python scripts/preview_telegram_wa_unify.py
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from whatsapp_ai_agent.config import get_settings
from whatsapp_ai_agent.db.models import Membership, Organization, User
from whatsapp_ai_agent.db.users_repository import find_telegram_only_users
from whatsapp_ai_agent.db.session import get_session_factory


def _session():
    settings = get_settings()
    factory = get_session_factory(settings)
    return factory()


def main() -> None:
    session = _session()
    tg_only = find_telegram_only_users(session)
    if not tg_only:
        print("No Telegram-only users found. Everyone already has a WhatsApp number or has none.")
        return

    print(f"Found {len(tg_only)} Telegram-only user(s):\n")
    for user in tg_only:
        memberships = session.scalars(
            select(Membership).where(Membership.user_id == user.id)
        ).all()
        orgs = []
        for m in memberships:
            org = session.get(Organization, m.org_id)
            orgs.append(f"{org.name} ({m.role})" if org else str(m.org_id))
        print(f"- User {user.id}")
        print(f"    display_name : {user.display_name}")
        print(f"    telegram_id  : {user.telegram_user_id}")
        print(f"    phone_number : {user.phone_number}")
        print(f"    orgs         : {', '.join(orgs) or 'NONE'}")
    print("\nTo unify, an admin can either:")
    print("  * set the person's WhatsApp number on this same user row (no merge needed), or")
    print("  * POST /dashboard-api/admin/merge-users with this user as source and the")
    print("    WhatsApp user as target, if a separate WhatsApp-only row already exists.")


if __name__ == "__main__":
    main()
