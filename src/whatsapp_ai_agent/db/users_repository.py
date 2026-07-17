"""User identity merge for multi-channel unification.

Doceebot keeps one ``User`` row that may carry both a ``telegram_user_id`` and a
``phone_number``. Work logs, conversations and raw inbound messages are keyed by
``user_id`` (not by channel), so once two channels point at the same ``User`` the
history is unified automatically.

When the same person was onboarded twice (once on Telegram, once on WhatsApp) two
``User`` rows exist with split histories. ``merge_users`` folds the *source* user
into the *target* user: every child record is re-pointed to the target, the source
identifier is preserved on the target row, and the now-empty source row is removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from whatsapp_ai_agent.db.models import (
    ConversationSession,
    DeveloperEscalation,
    ManagedDocument,
    Membership,
    RawInboundMessage,
    User,
    WorkLogEntry,
)


class UserMergeError(ValueError):
    """Raised when a merge is refused because it would corrupt routing or data."""


@dataclass(frozen=True)
class UserMergeResult:
    target_user_id: UUID
    source_user_id: UUID
    work_logs_moved: int
    conversations_moved: int
    raw_messages_moved: int
    escalations_moved: int
    documents_moved: int
    memberships_moved: int
    target_telegram_user_id: str | None
    target_phone_number: str | None


def _org_ids_for_user(db_session: Session, user_id: UUID) -> set[UUID]:
    return {
        m.org_id
        for m in db_session.scalars(
            select(Membership).where(Membership.user_id == user_id)
        )
    }


def merge_users(
    db_session: Session,
    *,
    source_user_id: UUID,
    target_user_id: UUID,
    allow_cross_org: bool = False,
) -> UserMergeResult:
    """Fold ``source_user_id`` into ``target_user_id``.

    The target user survives. All work logs, conversations, raw inbound messages,
    escalations, managed documents and memberships owned by the source are
    re-pointed to the target, the source's channel identifiers/email are preserved
    on the target, and the empty source row is deleted.

    Raises:
        UserMergeError: if the two users are the same, if either does not exist,
            or (unless ``allow_cross_org``) if they belong to different
            organizations, which would break automatic bot routing.
    """
    if source_user_id == target_user_id:
        raise UserMergeError("Cannot merge a user into itself.")

    source = db_session.get(User, source_user_id)
    target = db_session.get(User, target_user_id)
    if source is None or target is None:
        raise UserMergeError("Both source and target users must exist.")

    source_orgs = _org_ids_for_user(db_session, source.id)
    target_orgs = _org_ids_for_user(db_session, target.id)
    if not allow_cross_org and source_orgs != target_orgs:
        raise UserMergeError(
            "Source and target users belong to different organizations. "
            "Cross-organization merges are refused because they break bot routing."
        )

    # Capture the source's original identity values before we clear them, so we
    # can copy them onto the target afterward.
    source_originals = {
        "telegram_user_id": source.telegram_user_id,
        "phone_number": source.phone_number,
        "email": source.email,
    }

    # Preserve the source's identity fields on the target if the target lacks them.
    # We must clear them on the SOURCE first and flush, because SQLite's UNIQUE
    # constraint rejects having both rows hold the same value even transiently
    # within one transaction. Clearing source before copying to target keeps the
    # window collision-free.
    if not target.telegram_user_id and source.telegram_user_id:
        source.telegram_user_id = None
    if not target.phone_number and source.phone_number:
        source.phone_number = None
    if not target.email and source.email:
        source.email = None
    if not target.display_name and source.display_name:
        target.display_name = source.display_name
    db_session.flush()

    # Copy the source's identity onto the (now-empty) target slots.
    if target.telegram_user_id is None and source_originals["telegram_user_id"]:
        target.telegram_user_id = source_originals["telegram_user_id"]
    if target.phone_number is None and source_originals["phone_number"]:
        target.phone_number = source_originals["phone_number"]
    if target.email is None and source_originals["email"]:
        target.email = source_originals["email"]
    db_session.flush()

    # Re-point every child record to the surviving target user. Because a merge is
    # only permitted within a single organization, org_id stays constant and does
    # not need to be rewritten.
    work_logs_moved = _repoint(db_session, WorkLogEntry, "user_id", source.id, target.id)
    conversations_moved = _repoint(db_session, ConversationSession, "user_id", source.id, target.id)
    raw_messages_moved = _repoint(db_session, RawInboundMessage, "user_id", source.id, target.id)
    escalations_moved = _repoint(db_session, DeveloperEscalation, "user_id", source.id, target.id)
    documents_moved = _repoint(db_session, ManagedDocument, "owner_user_id", source.id, target.id)

    # Memberships: move source memberships onto target, keeping target's role when
    # both belong to the same org.
    memberships_moved = 0
    for membership in db_session.scalars(
        select(Membership).where(Membership.user_id == source.id)
    ):
        existing = db_session.scalar(
            select(Membership).where(
                Membership.org_id == membership.org_id,
                Membership.user_id == target.id,
            )
        )
        if existing is not None:
            db_session.delete(membership)
        else:
            membership.user_id = target.id
            db_session.add(membership)
        memberships_moved += 1

    # Capture ids/values before the source row is removed (the ORM object becomes
    # detached once the row is gone). Delete via a Core statement so the ORM does
    # not re-persist the source's attributes.
    source_id = source.id
    target_id = target.id
    target_tg = target.telegram_user_id
    target_phone = target.phone_number
    db_session.flush()
    db_session.execute(User.__table__.delete().where(User.__table__.c.id == source_id))
    db_session.flush()
    db_session.expunge(source)

    return UserMergeResult(
        target_user_id=target_id,
        source_user_id=source_id,
        work_logs_moved=work_logs_moved,
        conversations_moved=conversations_moved,
        raw_messages_moved=raw_messages_moved,
        escalations_moved=escalations_moved,
        documents_moved=documents_moved,
        memberships_moved=memberships_moved,
        target_telegram_user_id=target_tg,
        target_phone_number=target_phone,
    )


def _repoint(
    db_session: Session,
    model: type,
    column: str,
    source_id: UUID,
    target_id: UUID,
) -> int:
    """Update ``column`` from ``source_id`` to ``target_id`` and return rows changed."""
    table = model.__table__
    stmt = table.update().where(getattr(table.c, column) == source_id).values(
        **{column: target_id}
    )
    return db_session.execute(stmt).rowcount


def find_telegram_only_users(db_session: Session) -> list[User]:
    """Users that have a Telegram id but no WhatsApp phone (candidates to link)."""
    return list(
        db_session.scalars(
            select(User).where(
                User.telegram_user_id.is_not(None),
                User.phone_number.is_(None),
            )
        )
    )


def find_users_sharing_identifier(
    db_session: Session,
    *,
    telegram_user_id: str | None = None,
    phone_number: str | None = None,
) -> list[User]:
    """Return all users matching the given identifier(s), for split-account detection."""
    clauses = []
    if telegram_user_id:
        clauses.append(User.telegram_user_id == telegram_user_id)
    if phone_number:
        candidates = {phone_number, phone_number.removeprefix("+")}
        clauses.append(User.phone_number.in_(candidates))
    if not clauses:
        return []
    return list(db_session.scalars(select(User).where(or_(*clauses))))
