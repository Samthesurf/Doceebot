import json
import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.db.models import Membership, Organization, User
from whatsapp_ai_agent.db.session import get_db_session
from whatsapp_ai_agent.memory.session_search import SessionSearcher

router = APIRouter(prefix="/dashboard-api", tags=["dashboard"])
_GOOGLE_REQUEST = google_requests.Request()


class DashboardUser(BaseModel):
    uid: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None


class MetricCard(BaseModel):
    label: str
    value: str | int | float
    helper: str | None = None
    tone: str = "neutral"


class OverviewResponse(BaseModel):
    user: DashboardUser
    generated_at: datetime
    cards: list[MetricCard]
    ux_metrics: dict[str, float | int | str | None]
    recent_escalations: list[dict[str, object]]
    document_breakdown: list[dict[str, object]]
    session_breakdown: list[dict[str, object]]


class OrganizationDashboardRow(BaseModel):
    id: UUID
    name: str
    created_at: datetime | None = None
    member_count: int = 0
    document_count: int = 0
    work_log_count: int = 0
    conversation_count: int = 0
    active_session_count: int = 0


class OrganizationsResponse(BaseModel):
    organizations: list[OrganizationDashboardRow]


class DocumentDashboardRow(BaseModel):
    id: UUID
    org_id: UUID
    organization_name: str | None = None
    owner_user_id: UUID | None = None
    owner_name: str | None = None
    display_name: str
    filename: str
    document_kind: str
    content_type: str | None = None
    source_type: str
    status: str
    size_bytes: int | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    update_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentsDashboardResponse(BaseModel):
    documents: list[DocumentDashboardRow]


class EscalationDashboardRow(BaseModel):
    id: UUID
    conversation_id: UUID | None = None
    org_id: UUID | None = None
    organization_name: str | None = None
    user_id: UUID | None = None
    user_name: str | None = None
    platform: str | None = None
    report_text: str
    status: str
    destination: str | None = None
    error_text: str | None = None
    turn_count: int = 0
    work_log_count: int = 0
    created_at: datetime | None = None
    sent_at: datetime | None = None


class EscalationsResponse(BaseModel):
    escalations: list[EscalationDashboardRow]


class ConversationLogRow(BaseModel):
    conversation_id: UUID
    org_id: UUID | None = None
    organization_name: str | None = None
    user_id: UUID | None = None
    user_name: str | None = None
    platform: str | None = None
    status: str | None = None
    started_at: datetime | None = None
    last_message_at: datetime | None = None
    turn_count: int = 0
    work_log_count: int = 0
    escalation_count: int = 0
    turns: list[dict[str, object]] = Field(default_factory=list)


class LogsResponse(BaseModel):
    conversations: list[ConversationLogRow]


class SessionSearchResultRow(BaseModel):
    source_id: str
    session_id: str
    score: float
    snippet: str
    result_type: str
    work_log_title: str | None = None
    work_log_date: str | None = None
    turn_body_preview: str | None = None
    session_started_at: datetime | None = None
    session_status: str | None = None
    display_title: str
    display_date: str


class SessionSearchResponse(BaseModel):
    query: str
    org_id: UUID
    user_id: UUID | None = None
    results: list[SessionSearchResultRow]


class ManageableOrganizationRow(BaseModel):
    id: UUID
    name: str
    role: str
    member_count: int = 0


class DashboardAdminAccessResponse(BaseModel):
    linked_user_id: UUID
    linked_user_name: str | None = None
    linked_user_email: str
    organizations: list[ManageableOrganizationRow]


class OrganizationMemberRow(BaseModel):
    user_id: UUID
    display_name: str | None = None
    phone_number: str | None = None
    telegram_user_id: str | None = None
    role: str
    created_at: datetime | None = None


class OrganizationMembersResponse(BaseModel):
    org_id: UUID
    organization_name: str
    members: list[OrganizationMemberRow]


class OrgUserCreateRequest(BaseModel):
    org_id: UUID
    platform: str
    identifier: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)


class OrgUserCreateResponse(BaseModel):
    org_id: UUID
    organization_name: str
    user: OrganizationMemberRow
    created_user: bool
    created_membership: bool
    updated_membership_role: bool


class AdminEmailLinkRequest(BaseModel):
    org_id: UUID
    email: str = Field(min_length=3, max_length=255)
    platform: str
    identifier: str = Field(min_length=1, max_length=255)
    role: str = "org_admin"
    display_name: str | None = Field(default=None, max_length=255)


class AdminEmailLinkResponse(BaseModel):
    org_id: UUID
    organization_name: str
    user: OrganizationMemberRow
    email: str
    email_previously_set: bool
    created_user: bool
    created_membership: bool
    updated_membership_role: bool
    updated_membership_email: bool


class TokenUsageTotals(BaseModel):
    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    average_total_tokens: float = 0.0
    last_event_at: datetime | None = None
    estimated: bool = True


class TokenUsageBreakdownRow(BaseModel):
    provider: str
    model: str
    purpose: str | None = None
    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    average_total_tokens: float = 0.0
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    estimated: bool = True


class TokenUsageDailyRow(BaseModel):
    date: str
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    error_count: int = 0
    estimated: bool = True


class TokenUsageRecentRow(BaseModel):
    id: UUID
    conversation_id: UUID | None = None
    provider: str
    model: str
    purpose: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    status: str
    created_at: datetime | None = None
    estimated: bool = True


class TokenUsageResponse(BaseModel):
    generated_at: datetime
    window_days: int
    note: str
    totals: TokenUsageTotals
    by_model: list[TokenUsageBreakdownRow]
    by_purpose: list[TokenUsageBreakdownRow]
    daily: list[TokenUsageDailyRow]
    recent: list[TokenUsageRecentRow]


def _json_loads(value: str | None, fallback: object) -> object:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _allowed_emails(settings: Settings) -> set[str]:
    return {
        email.strip().lower()
        for email in (settings.dashboard_allowed_emails or "").split(",")
        if email.strip()
    }


_ADMIN_ROLES = {"admin", "org_admin", "manager"}
_ALLOWED_MEMBER_ROLES = {"worker", "supervisor", "manager", "org_admin", "admin"}


def _normalize_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized == "admin":
        return "org_admin"
    if normalized not in _ALLOWED_MEMBER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Role must be one of worker, supervisor, manager, or org_admin",
        )
    return normalized


def _normalize_platform(platform: str) -> str:
    normalized = platform.strip().lower()
    if normalized in {"whatsapp", "whatsapp_twilio"}:
        return "whatsapp"
    if normalized == "telegram":
        return "telegram"
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Platform must be whatsapp or telegram",
    )


def _normalize_whatsapp_identifier(value: str) -> str:
    raw = value.strip()
    without_prefix = raw.removeprefix("whatsapp:").strip()
    digits = "".join(ch for ch in without_prefix if ch.isdigit())
    if digits:
        return f"+{digits}"
    if not without_prefix:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="WhatsApp number cannot be empty",
        )
    return without_prefix


def _normalize_telegram_identifier(value: str) -> str:
    normalized = value.strip().lstrip("@")
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Telegram user ID cannot be empty",
        )
    return normalized


def _find_user_by_whatsapp(db_session: Session, identifier: str) -> User | None:
    candidates = {identifier, identifier.removeprefix("+")}
    candidates = {candidate for candidate in candidates if candidate}
    user = db_session.scalar(select(User).where(User.phone_number.in_(candidates)).limit(1))
    if user is not None:
        return user
    normalized = "".join(ch for ch in identifier if ch.isdigit())
    if not normalized:
        return None
    for possible_user in db_session.scalars(select(User).where(User.phone_number.is_not(None))):
        current = "".join(ch for ch in (possible_user.phone_number or "") if ch.isdigit())
        if current == normalized:
            return possible_user
    return None


def _default_display_name(platform: str, identifier: str) -> str:
    if platform == "telegram":
        return f"Telegram User {identifier}"
    return f"WhatsApp User {identifier}"


def _normalize_email(value: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized or "@" not in normalized or " " in normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid dashboard login email is required",
        )
    return normalized


def _require_admin_memberships(
    dashboard_user: DashboardUser,
    db_session: Session,
) -> tuple[User, list[tuple[Membership, Organization]]]:
    email = (dashboard_user.email or "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dashboard account must have an email address to manage organization users",
        )

    linked_user = db_session.scalar(
        select(User).where(func.lower(User.email) == email).limit(1)
    )
    if linked_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This dashboard account is not linked to an organization admin user record",
        )

    memberships = list(
        db_session.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.org_id)
            .where(Membership.user_id == linked_user.id)
        )
    )
    admin_memberships = [
        (membership, organization)
        for membership, organization in memberships
        if membership.role.lower() in _ADMIN_ROLES
    ]
    if not admin_memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an organization admin for any managed workspace",
        )
    return linked_user, admin_memberships


def _require_admin_org(
    dashboard_user: DashboardUser,
    db_session: Session,
    org_id: UUID,
) -> tuple[User, Membership, Organization]:
    linked_user, admin_memberships = _require_admin_memberships(dashboard_user, db_session)
    for membership, organization in admin_memberships:
        if organization.id == org_id:
            return linked_user, membership, organization
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have admin access to that organization",
    )


async def require_dashboard_user(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> DashboardUser:
    if not settings.firebase_project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard Firebase project is not configured",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Firebase ID token",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = id_token.verify_firebase_token(
            token,
            _GOOGLE_REQUEST,
            audience=settings.firebase_project_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token",
        ) from exc

    email = claims.get("email")
    allowed = _allowed_emails(settings)
    if allowed and (not isinstance(email, str) or email.lower() not in allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This Firebase account is not allowed to view the dashboard",
        )
    return DashboardUser(
        uid=str(claims.get("user_id") or claims.get("sub") or ""),
        email=email if isinstance(email, str) else None,
        name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        picture=claims.get("picture") if isinstance(claims.get("picture"), str) else None,
    )


def require_logs_password(
    x_logs_password: Annotated[str | None, Header(alias="X-Logs-Password")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.dashboard_logs_password
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Logs password is not configured",
        )
    if not x_logs_password or not secrets.compare_digest(x_logs_password, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid logs password",
        )


def _scalar_int(db_session: Session, sql: str) -> int:
    return int(db_session.execute(text(sql)).scalar_one() or 0)


def _scalar_float(db_session: Session, sql: str) -> float:
    value = db_session.execute(text(sql)).scalar_one()
    return float(value or 0)


def _pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) * 100 / float(denominator), 1)


@router.get("/me", response_model=DashboardUser)
async def get_dashboard_me(
    user: DashboardUser = Depends(require_dashboard_user),
) -> DashboardUser:
    return user


@router.get("/overview", response_model=OverviewResponse)
async def get_dashboard_overview(
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> OverviewResponse:
    organizations = _scalar_int(db_session, "SELECT count(*) FROM organizations")
    users = _scalar_int(db_session, "SELECT count(*) FROM users")
    documents = _scalar_int(db_session, "SELECT count(*) FROM managed_documents")
    active_sessions = _scalar_int(
        db_session,
        "SELECT count(*) FROM conversation_sessions WHERE status = 'active'",
    )
    pending_escalations = _scalar_int(
        db_session,
        "SELECT count(*) FROM developer_escalations WHERE status IN ('pending', 'failed')",
    )
    draft_logs = _scalar_int(
        db_session,
        "SELECT count(*) FROM work_log_entries WHERE confirmation_status = 'draft'",
    )
    confirmed_logs = _scalar_int(
        db_session,
        "SELECT count(*) FROM work_log_entries WHERE confirmation_status = 'confirmed'",
    )
    inbound_turns = _scalar_int(
        db_session,
        "SELECT count(*) FROM conversation_turns WHERE direction = 'inbound'",
    )
    chat_parse_total = _scalar_int(
        db_session,
        "SELECT count(*) FROM llm_audit_logs WHERE purpose = 'chat_parse'",
    )
    chat_parse_fallbacks = _scalar_int(
        db_session,
        """
        SELECT count(*)
        FROM llm_audit_logs
        WHERE purpose = 'chat_parse'
          AND output_json IS NOT NULL
          AND output_json::jsonb ->> 'intent' = 'other'
        """,
    )
    correction_turns = _scalar_int(
        db_session,
        """
        SELECT count(*)
        FROM conversation_turns
        WHERE direction = 'inbound'
          AND (
            metadata_json::jsonb ->> 'command' = 'feedback'
            OR body_text ILIKE '%wrong%'
            OR body_text ILIKE '%not correct%'
            OR body_text ILIKE 'edit %'
          )
        """,
    )
    avg_session_hours = _scalar_float(
        db_session,
        """
        SELECT avg(extract(epoch from (coalesce(closed_at, last_message_at) - started_at)) / 3600.0)
        FROM conversation_sessions
        WHERE started_at IS NOT NULL AND last_message_at IS NOT NULL
        """,
    )
    media_audits = _scalar_int(
        db_session,
        "SELECT count(*) FROM llm_audit_logs WHERE purpose = 'media_extraction'",
    )

    doc_breakdown = [
        dict(row)
        for row in db_session.execute(
            text(
                """
                SELECT document_kind AS label, count(*) AS value
                FROM managed_documents
                GROUP BY document_kind
                ORDER BY value DESC, label ASC
                """
            )
        ).mappings()
    ]
    session_breakdown = [
        dict(row)
        for row in db_session.execute(
            text(
                """
                SELECT status AS label, count(*) AS value
                FROM conversation_sessions
                GROUP BY status
                ORDER BY value DESC, label ASC
                """
            )
        ).mappings()
    ]
    recent_escalations = [
        dict(row)
        for row in db_session.execute(
            text(
                """
                SELECT e.id::text AS id, e.report_text, e.status, e.platform,
                       e.created_at, o.name AS organization_name, u.display_name AS user_name
                FROM developer_escalations e
                LEFT JOIN organizations o ON o.id = e.org_id
                LEFT JOIN users u ON u.id = e.user_id
                ORDER BY e.created_at DESC
                LIMIT 5
                """
            )
        ).mappings()
    ]

    total_logs = draft_logs + confirmed_logs
    return OverviewResponse(
        user=user,
        generated_at=datetime.now(UTC),
        cards=[
            MetricCard(label="Organizations", value=organizations, helper="Tenants connected"),
            MetricCard(label="Users", value=users, helper="Known bot users"),
            MetricCard(label="Documents", value=documents, helper="Uploaded and generated files"),
            MetricCard(label="Active sessions", value=active_sessions, helper="13-hour workspaces"),
            MetricCard(
                label="Escalations",
                value=pending_escalations,
                helper="Pending or failed developer reports",
                tone="warning" if pending_escalations else "neutral",
            ),
        ],
        ux_metrics={
            "unconfirmed_draft_rate": _pct(draft_logs, total_logs),
            "correction_rate": _pct(correction_turns, inbound_turns),
            "fallback_rate": _pct(chat_parse_fallbacks, chat_parse_total),
            "messages_per_confirmed_log": round(inbound_turns / confirmed_logs, 2)
            if confirmed_logs
            else 0,
            "media_processing_events": media_audits,
            "average_session_hours": round(avg_session_hours, 2),
            "draft_logs": draft_logs,
            "confirmed_logs": confirmed_logs,
        },
        recent_escalations=recent_escalations,
        document_breakdown=doc_breakdown,
        session_breakdown=session_breakdown,
    )


@router.get("/organizations", response_model=OrganizationsResponse)
async def list_dashboard_organizations(
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> OrganizationsResponse:
    _ = user
    rows = db_session.execute(
        text(
            """
            SELECT o.id, o.name, o.created_at,
                   count(DISTINCT m.user_id) AS member_count,
                   count(DISTINCT d.id) AS document_count,
                   count(DISTINCT w.id) AS work_log_count,
                   count(DISTINCT c.id) AS conversation_count,
                   count(DISTINCT c.id) FILTER (WHERE c.status = 'active') AS active_session_count
            FROM organizations o
            LEFT JOIN memberships m ON m.org_id = o.id
            LEFT JOIN managed_documents d ON d.org_id = o.id
            LEFT JOIN work_log_entries w ON w.org_id = o.id
            LEFT JOIN conversation_sessions c ON c.org_id = o.id
            GROUP BY o.id, o.name, o.created_at
            ORDER BY o.created_at DESC
            """
        )
    ).mappings()
    return OrganizationsResponse(
        organizations=[OrganizationDashboardRow(**dict(row)) for row in rows]
    )


@router.get("/admin/access", response_model=DashboardAdminAccessResponse)
async def get_dashboard_admin_access(
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> DashboardAdminAccessResponse:
    linked_user, admin_memberships = _require_admin_memberships(user, db_session)
    organization_rows = []
    for membership, organization in sorted(
        admin_memberships,
        key=lambda item: (item[1].created_at or datetime.min.replace(tzinfo=UTC), item[1].name),
        reverse=True,
    ):
        member_count = int(
            db_session.execute(
                select(func.count(Membership.user_id)).where(Membership.org_id == organization.id)
            ).scalar_one()
            or 0
        )
        organization_rows.append(
            ManageableOrganizationRow(
                id=organization.id,
                name=organization.name,
                role=_normalize_role(membership.role),
                member_count=member_count,
            )
        )
    return DashboardAdminAccessResponse(
        linked_user_id=linked_user.id,
        linked_user_name=linked_user.display_name,
        linked_user_email=linked_user.email or (user.email or ""),
        organizations=organization_rows,
    )


@router.get("/admin/users", response_model=OrganizationMembersResponse)
async def list_dashboard_org_users(
    org_id: UUID,
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> OrganizationMembersResponse:
    _, _, organization = _require_admin_org(user, db_session, org_id)
    memberships = list(
        db_session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.org_id == org_id)
            .order_by(User.created_at.desc(), User.display_name.asc())
        )
    )
    return OrganizationMembersResponse(
        org_id=organization.id,
        organization_name=organization.name,
        members=[
            OrganizationMemberRow(
                user_id=member_user.id,
                display_name=member_user.display_name,
                phone_number=member_user.phone_number,
                telegram_user_id=member_user.telegram_user_id,
                role=_normalize_role(membership.role),
                created_at=member_user.created_at,
            )
            for membership, member_user in memberships
        ],
    )


@router.post(
    "/admin/users",
    response_model=OrgUserCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_dashboard_org_user(
    payload: OrgUserCreateRequest,
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> OrgUserCreateResponse:
    _, _, organization = _require_admin_org(user, db_session, payload.org_id)
    role = _normalize_role(payload.role)
    platform = _normalize_platform(payload.platform)
    display_name = (payload.display_name or "").strip() or None

    existing_user = None
    normalized_identifier: str
    if platform == "telegram":
        normalized_identifier = _normalize_telegram_identifier(payload.identifier)
        existing_user = db_session.scalar(
            select(User).where(User.telegram_user_id == normalized_identifier).limit(1)
        )
    else:
        normalized_identifier = _normalize_whatsapp_identifier(payload.identifier)
        existing_user = _find_user_by_whatsapp(db_session, normalized_identifier)

    created_user = False
    created_membership = False
    updated_membership_role = False

    if existing_user is None:
        existing_user = User(
            display_name=display_name or _default_display_name(platform, normalized_identifier),
            phone_number=normalized_identifier if platform == "whatsapp" else None,
            telegram_user_id=normalized_identifier if platform == "telegram" else None,
        )
        db_session.add(existing_user)
        db_session.flush()
        created_user = True
    else:
        other_membership = db_session.scalar(
            select(Membership)
            .where(Membership.user_id == existing_user.id, Membership.org_id != organization.id)
            .limit(1)
        )
        if other_membership is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "That identifier already belongs to a different organization. "
                    "Cross-organization memberships break automatic bot routing."
                ),
            )
        if display_name and display_name != existing_user.display_name:
            existing_user.display_name = display_name
        if platform == "whatsapp" and not existing_user.phone_number:
            existing_user.phone_number = normalized_identifier
        if platform == "telegram" and not existing_user.telegram_user_id:
            existing_user.telegram_user_id = normalized_identifier

    membership = db_session.scalar(
        select(Membership)
        .where(Membership.user_id == existing_user.id, Membership.org_id == organization.id)
        .limit(1)
    )
    if membership is None:
        membership = Membership(org_id=organization.id, user_id=existing_user.id, role=role)
        db_session.add(membership)
        created_membership = True
    elif membership.role != role:
        membership.role = role
        updated_membership_role = True

    db_session.commit()
    db_session.refresh(existing_user)

    return OrgUserCreateResponse(
        org_id=organization.id,
        organization_name=organization.name,
        user=OrganizationMemberRow(
            user_id=existing_user.id,
            display_name=existing_user.display_name,
            phone_number=existing_user.phone_number,
            telegram_user_id=existing_user.telegram_user_id,
            role=_normalize_role(membership.role),
            created_at=existing_user.created_at,
        ),
        created_user=created_user,
        created_membership=created_membership,
        updated_membership_role=updated_membership_role,
    )


@router.post(
    "/admin/link-email",
    response_model=AdminEmailLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_dashboard_admin_email(
    payload: AdminEmailLinkRequest,
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> AdminEmailLinkResponse:
    """Link a dashboard login email to a bot user record so the linked person
    can sign in to the dashboard and, with an admin membership, manage the org."""
    _, _, organization = _require_admin_org(user, db_session, payload.org_id)
    role = _normalize_role(payload.role)
    platform = _normalize_platform(payload.platform)
    display_name = (payload.display_name or "").strip() or None

    email = _normalize_email(payload.email)

    existing_user = None
    normalized_identifier: str
    if platform == "telegram":
        normalized_identifier = _normalize_telegram_identifier(payload.identifier)
        existing_user = db_session.scalar(
            select(User).where(User.telegram_user_id == normalized_identifier).limit(1)
        )
    else:
        normalized_identifier = _normalize_whatsapp_identifier(payload.identifier)
        existing_user = _find_user_by_whatsapp(db_session, normalized_identifier)

    created_user = False
    created_membership = False
    updated_membership_role = False
    updated_membership_email = False

    if existing_user is None:
        existing_user = User(
            display_name=display_name or _default_display_name(platform, normalized_identifier),
            phone_number=normalized_identifier if platform == "whatsapp" else None,
            telegram_user_id=normalized_identifier if platform == "telegram" else None,
        )
        db_session.add(existing_user)
        db_session.flush()
        created_user = True
    else:
        other_membership = db_session.scalar(
            select(Membership)
            .where(Membership.user_id == existing_user.id, Membership.org_id != organization.id)
            .limit(1)
        )
        if other_membership is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "That identifier already belongs to a different organization. "
                    "Cross-organization memberships break automatic bot routing."
                ),
            )
        if display_name and display_name != existing_user.display_name:
            existing_user.display_name = display_name
        if platform == "whatsapp" and not existing_user.phone_number:
            existing_user.phone_number = normalized_identifier
        if platform == "telegram" and not existing_user.telegram_user_id:
            existing_user.telegram_user_id = normalized_identifier

    email_owner = db_session.scalar(
        select(User)
        .where(func.lower(User.email) == email, User.id != existing_user.id)
        .limit(1)
    )
    if email_owner is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already linked to a different user record.",
        )
    email_previously_set = bool(existing_user.email and existing_user.email.lower() == email)
    if not email_previously_set:
        existing_user.email = email
        updated_membership_email = True

    membership = db_session.scalar(
        select(Membership).where(
            Membership.user_id == existing_user.id,
            Membership.org_id == organization.id,
        ).limit(1)
    )
    if membership is None:
        membership = Membership(org_id=organization.id, user_id=existing_user.id, role=role)
        db_session.add(membership)
        created_membership = True
    elif membership.role != role:
        membership.role = role
        updated_membership_role = True

    db_session.commit()
    db_session.refresh(existing_user)

    return AdminEmailLinkResponse(
        org_id=organization.id,
        organization_name=organization.name,
        user=OrganizationMemberRow(
            user_id=existing_user.id,
            display_name=existing_user.display_name,
            phone_number=existing_user.phone_number,
            telegram_user_id=existing_user.telegram_user_id,
            role=_normalize_role(membership.role),
            created_at=existing_user.created_at,
        ),
        email=email,
        email_previously_set=email_previously_set,
        created_user=created_user,
        created_membership=created_membership,
        updated_membership_role=updated_membership_role,
        updated_membership_email=updated_membership_email,
    )


@router.get("/documents", response_model=DocumentsDashboardResponse)
async def list_dashboard_documents(
    org_id: UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> DocumentsDashboardResponse:
    _ = user
    params: dict[str, object] = {"limit": limit}
    clauses = []
    if org_id is not None:
        clauses.append("d.org_id = :org_id")
        params["org_id"] = str(org_id)
    if status_filter:
        clauses.append("d.status = :status")
        params["status"] = status_filter
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = db_session.execute(
        text(
            f"""
            SELECT d.id, d.org_id, o.name AS organization_name, d.owner_user_id,
                   u.display_name AS owner_name, d.display_name, d.filename,
                   d.document_kind, d.content_type, d.source_type, d.status,
                   d.size_bytes, d.summary, d.tags_json, d.created_at, d.updated_at,
                   count(mu.id) AS update_count
            FROM managed_documents d
            LEFT JOIN organizations o ON o.id = d.org_id
            LEFT JOIN users u ON u.id = d.owner_user_id
            LEFT JOIN managed_document_updates mu ON mu.document_id = d.id
            {where}
            GROUP BY d.id, o.name, u.display_name
            ORDER BY d.updated_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    documents = []
    for row in rows:
        item = dict(row)
        item["tags"] = _json_loads(item.pop("tags_json", None), [])
        documents.append(DocumentDashboardRow(**item))
    return DocumentsDashboardResponse(documents=documents)


@router.get("/search", response_model=SessionSearchResponse)
async def search_dashboard_sessions(
    q: Annotated[str, Query(min_length=1, max_length=300)],
    org_id: UUID,
    user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> SessionSearchResponse:
    _ = user
    searcher = SessionSearcher(db_session)
    results = searcher.search(
        query=q,
        org_id=org_id,
        user_id=user_id,
        limit=limit,
    )
    return SessionSearchResponse(
        query=q,
        org_id=org_id,
        user_id=user_id,
        results=[
            SessionSearchResultRow(
                source_id=result.source_id,
                session_id=result.session_id,
                score=result.score,
                snippet=result.snippet,
                result_type=result.result_type,
                work_log_title=result.work_log_title,
                work_log_date=result.work_log_date,
                turn_body_preview=result.turn_body_preview,
                session_started_at=result.session_started_at,
                session_status=result.session_status,
                display_title=result.display_title,
                display_date=result.display_date,
            )
            for result in results
        ],
    )


@router.get("/escalations", response_model=EscalationsResponse)
async def list_dashboard_escalations(
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> EscalationsResponse:
    _ = user
    params: dict[str, object] = {"limit": limit}
    where = ""
    if status_filter:
        where = "WHERE e.status = :status"
        params["status"] = status_filter
    rows = db_session.execute(
        text(
            f"""
            SELECT e.id, e.conversation_id, e.org_id, o.name AS organization_name,
                   e.user_id, u.display_name AS user_name, e.platform, e.report_text,
                   e.status, e.destination, e.error_text, e.created_at, e.sent_at,
                   count(DISTINCT t.id) AS turn_count,
                   count(DISTINCT w.id) AS work_log_count
            FROM developer_escalations e
            LEFT JOIN organizations o ON o.id = e.org_id
            LEFT JOIN users u ON u.id = e.user_id
            LEFT JOIN conversation_turns t ON t.conversation_id = e.conversation_id
            LEFT JOIN work_log_entries w ON w.conversation_id = e.conversation_id
            {where}
            GROUP BY e.id, o.name, u.display_name
            ORDER BY e.created_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return EscalationsResponse(escalations=[EscalationDashboardRow(**dict(row)) for row in rows])


_TOKEN_USAGE_NOTE = (
    "Token counts are estimated from persisted, redacted LLM audit payload sizes "
    "because historical provider usage metadata was not stored. Counts are safe for "
    "trend monitoring and cost anomaly detection, but they are not billing-grade totals."
)

_TOKEN_USAGE_CTE = """
WITH usage AS (
    SELECT id,
           conversation_id,
           provider,
           model,
           purpose,
           created_at,
           error_text,
           GREATEST(1, CEIL(length(COALESCE(input_json, '')) / 4.0))::int AS input_tokens,
           GREATEST(0, CEIL(length(COALESCE(output_json, '')) / 4.0))::int AS output_tokens
    FROM llm_audit_logs
    WHERE created_at >= now() - (:window_days * interval '1 day')
)
"""


@router.get("/token-usage", response_model=TokenUsageResponse)
async def get_dashboard_token_usage(
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    user: DashboardUser = Depends(require_dashboard_user),
    db_session: Session = Depends(get_db_session),
) -> TokenUsageResponse:
    _ = user
    params: dict[str, object] = {"window_days": window_days, "limit": limit}
    totals_row = dict(
        db_session.execute(
            text(
                _TOKEN_USAGE_CTE
                + """
                SELECT count(*)::int AS request_count,
                       count(*) FILTER (WHERE error_text IS NULL)::int AS success_count,
                       count(*) FILTER (WHERE error_text IS NOT NULL)::int AS error_count,
                       COALESCE(sum(input_tokens), 0)::int AS input_tokens,
                       COALESCE(sum(output_tokens), 0)::int AS output_tokens,
                       COALESCE(sum(input_tokens + output_tokens), 0)::int AS total_tokens,
                       round(COALESCE(avg(input_tokens + output_tokens), 0)::numeric, 2)::float
                           AS average_total_tokens,
                       max(created_at) AS last_event_at
                FROM usage
                """
            ),
            params,
        ).mappings().one()
    )
    by_model = [
        TokenUsageBreakdownRow(**dict(row))
        for row in db_session.execute(
            text(
                _TOKEN_USAGE_CTE
                + """
                SELECT provider,
                       model,
                       NULL::text AS purpose,
                       count(*)::int AS request_count,
                       count(*) FILTER (WHERE error_text IS NULL)::int AS success_count,
                       count(*) FILTER (WHERE error_text IS NOT NULL)::int AS error_count,
                       COALESCE(sum(input_tokens), 0)::int AS input_tokens,
                       COALESCE(sum(output_tokens), 0)::int AS output_tokens,
                       COALESCE(sum(input_tokens + output_tokens), 0)::int AS total_tokens,
                       round(COALESCE(avg(input_tokens + output_tokens), 0)::numeric, 2)::float
                           AS average_total_tokens,
                       min(created_at) AS first_seen_at,
                       max(created_at) AS last_seen_at
                FROM usage
                GROUP BY provider, model
                ORDER BY total_tokens DESC, request_count DESC, provider ASC, model ASC
                LIMIT :limit
                """
            ),
            params,
        ).mappings()
    ]
    by_purpose = [
        TokenUsageBreakdownRow(**dict(row))
        for row in db_session.execute(
            text(
                _TOKEN_USAGE_CTE
                + """
                SELECT 'all'::text AS provider,
                       'all'::text AS model,
                       purpose,
                       count(*)::int AS request_count,
                       count(*) FILTER (WHERE error_text IS NULL)::int AS success_count,
                       count(*) FILTER (WHERE error_text IS NOT NULL)::int AS error_count,
                       COALESCE(sum(input_tokens), 0)::int AS input_tokens,
                       COALESCE(sum(output_tokens), 0)::int AS output_tokens,
                       COALESCE(sum(input_tokens + output_tokens), 0)::int AS total_tokens,
                       round(COALESCE(avg(input_tokens + output_tokens), 0)::numeric, 2)::float
                           AS average_total_tokens,
                       min(created_at) AS first_seen_at,
                       max(created_at) AS last_seen_at
                FROM usage
                GROUP BY purpose
                ORDER BY total_tokens DESC, request_count DESC, purpose ASC
                LIMIT :limit
                """
            ),
            params,
        ).mappings()
    ]
    daily = [
        TokenUsageDailyRow(**dict(row))
        for row in db_session.execute(
            text(
                _TOKEN_USAGE_CTE
                + """
                SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS date,
                       count(*)::int AS request_count,
                       COALESCE(sum(input_tokens), 0)::int AS input_tokens,
                       COALESCE(sum(output_tokens), 0)::int AS output_tokens,
                       COALESCE(sum(input_tokens + output_tokens), 0)::int AS total_tokens,
                       count(*) FILTER (WHERE error_text IS NOT NULL)::int AS error_count
                FROM usage
                GROUP BY date_trunc('day', created_at)
                ORDER BY date ASC
                """
            ),
            params,
        ).mappings()
    ]
    recent = [
        TokenUsageRecentRow(**dict(row))
        for row in db_session.execute(
            text(
                _TOKEN_USAGE_CTE
                + """
                SELECT id,
                       conversation_id,
                       provider,
                       model,
                       purpose,
                       input_tokens,
                       output_tokens,
                       input_tokens + output_tokens AS total_tokens,
                       CASE WHEN error_text IS NULL THEN 'success' ELSE 'error' END AS status,
                       created_at
                FROM usage
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings()
    ]
    return TokenUsageResponse(
        generated_at=datetime.now(UTC),
        window_days=window_days,
        note=_TOKEN_USAGE_NOTE,
        totals=TokenUsageTotals(**totals_row),
        by_model=by_model,
        by_purpose=by_purpose,
        daily=daily,
        recent=recent,
    )


@router.get("/logs", response_model=LogsResponse)
async def list_dashboard_logs(
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
    user: DashboardUser = Depends(require_dashboard_user),
    _: None = Depends(require_logs_password),
    db_session: Session = Depends(get_db_session),
) -> LogsResponse:
    _user = user
    conversations = list(
        db_session.execute(
            text(
                """
                SELECT c.id AS conversation_id, c.org_id, o.name AS organization_name,
                       c.user_id, u.display_name AS user_name, c.platform, c.status,
                       c.started_at, c.last_message_at,
                       count(DISTINCT t.id) AS turn_count,
                       count(DISTINCT w.id) AS work_log_count,
                       count(DISTINCT e.id) AS escalation_count
                FROM conversation_sessions c
                LEFT JOIN organizations o ON o.id = c.org_id
                LEFT JOIN users u ON u.id = c.user_id
                LEFT JOIN conversation_turns t ON t.conversation_id = c.id
                LEFT JOIN work_log_entries w ON w.conversation_id = c.id
                LEFT JOIN developer_escalations e ON e.conversation_id = c.id
                GROUP BY c.id, o.name, u.display_name
                ORDER BY c.last_message_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings()
    )
    response_rows: list[ConversationLogRow] = []
    for row in conversations:
        item = dict(row)
        turns = [
            dict(turn)
            for turn in db_session.execute(
                text(
                    """
                    SELECT direction, platform, message_type, body_text, metadata_json,
                           occurred_at, created_at
                    FROM conversation_turns
                    WHERE conversation_id = :conversation_id
                    ORDER BY occurred_at ASC, created_at ASC
                    LIMIT 80
                    """
                ),
                {"conversation_id": item["conversation_id"]},
            ).mappings()
        ]
        for turn in turns:
            turn["metadata"] = _json_loads(turn.pop("metadata_json", None), {})
        item["turns"] = turns
        response_rows.append(ConversationLogRow(**item))
    return LogsResponse(conversations=response_rows)
