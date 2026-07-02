from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from whatsapp_ai_agent.core.events import InboundEvent
from whatsapp_ai_agent.db.models import Membership, User


@dataclass(frozen=True)
class TenantScope:
    org_id: str
    user_id: str | None = None


@dataclass(frozen=True)
class TenantResolution:
    event: InboundEvent
    resolved: bool
    reason: str | None = None


def require_org_scope(scope: TenantScope) -> str:
    if not scope.org_id:
        raise PermissionError("Event has no resolved organization")
    return scope.org_id


def _phone_candidates(value: str | None) -> set[str]:
    if not value:
        return set()
    raw = value.strip()
    without_prefix = raw.removeprefix("whatsapp:").strip()
    digits = "".join(ch for ch in without_prefix if ch.isdigit())
    candidates = {raw, without_prefix}
    if digits:
        candidates.update({digits, f"+{digits}", f"whatsapp:+{digits}"})
    return {candidate for candidate in candidates if candidate}


def _find_user_for_event(event: InboundEvent, db_session: Session) -> User | None:
    if event.platform == "telegram":
        return db_session.scalar(
            select(User).where(User.telegram_user_id == event.platform_user_id).limit(1)
        )

    candidates = _phone_candidates(event.platform_user_id) | _phone_candidates(
        event.platform_chat_id
    )
    if not candidates:
        return None
    user = db_session.scalar(select(User).where(User.phone_number.in_(candidates)).limit(1))
    if user is not None:
        return user

    normalized_candidates = {"".join(ch for ch in value if ch.isdigit()) for value in candidates}
    normalized_candidates.discard("")
    if not normalized_candidates:
        return None
    for possible_user in db_session.scalars(select(User).where(User.phone_number.is_not(None))):
        normalized_phone = "".join(ch for ch in (possible_user.phone_number or "") if ch.isdigit())
        if normalized_phone in normalized_candidates:
            return possible_user
    return None


def resolve_event_tenant_scope(event: InboundEvent, db_session: Session) -> TenantResolution:
    if event.org_id is not None and event.user_id is not None:
        return TenantResolution(event=event, resolved=True)

    user = _find_user_for_event(event, db_session)
    if user is None:
        return TenantResolution(
            event=event,
            resolved=False,
            reason="sender is not linked to a user",
        )

    memberships = list(
        db_session.scalars(select(Membership).where(Membership.user_id == user.id).limit(2))
    )
    if not memberships:
        return TenantResolution(
            event=event,
            resolved=False,
            reason="user has no organization membership",
        )
    if len(memberships) > 1:
        return TenantResolution(
            event=event.model_copy(update={"user_id": user.id}),
            resolved=False,
            reason="user belongs to multiple organizations and has no active selection",
        )

    membership = memberships[0]
    return TenantResolution(
        event=event.model_copy(update={"org_id": membership.org_id, "user_id": user.id}),
        resolved=True,
    )


def scope_ids(event: InboundEvent) -> tuple[UUID | None, UUID | None]:
    return event.org_id, event.user_id
