import json
import secrets
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.db.session import get_db_session

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
        generated_at=datetime.utcnow(),
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
