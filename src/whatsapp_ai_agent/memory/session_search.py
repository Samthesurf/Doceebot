# ruff: noqa: E501
"""Hybrid retrieval for past sessions, work logs, and conversation turns.

PostgreSQL path:
- full-text search via generated ``search_vector`` columns
- fuzzy matching via ``pg_trgm`` similarity()
- weighted fusion score for ranking

Fallback path:
- cross-database SQLAlchemy ``ILIKE`` / substring search for tests and non-Postgres

This module powers both:
1. explicit user search commands, e.g. ``search packaging line``
2. lightweight cross-session retrieval that is injected into LLM context so the bot
   can reference prior sessions when a user says things like "use the one from
   yesterday" or "make the report for that job I mentioned last week".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from whatsapp_ai_agent.db.models import ConversationSession, ConversationTurn, WorkLogEntry

logger = logging.getLogger(__name__)

_HYBRID_SEARCH_SQL = """\
WITH q AS (
    SELECT plainto_tsquery('english', :query) AS tsq
),
work_log_matches AS (
    SELECT
        wle.id                                                                       AS source_id,
        COALESCE(cs.id, wle.conversation_id, wle.id)                                 AS session_id,
        CASE
            WHEN wle.search_vector IS NOT NULL
             AND wle.search_vector @@ q.tsq
            THEN 0.7 * ts_rank_cd(wle.search_vector, q.tsq)
            ELSE 0.0
        END
        + 0.3 * GREATEST(
            similarity(COALESCE(wle.title, ''), :query),
            similarity(COALESCE(wle.description, ''), :query),
            similarity(COALESCE(wle.summary, ''), :query),
            similarity(COALESCE(wle.project, ''), :query),
            similarity(COALESCE(wle.site, ''), :query),
            similarity(COALESCE(wle.location_label, ''), :query),
            similarity(COALESCE(wle.category, ''), :query)
        )                                                                            AS score,
        CASE
            WHEN wle.search_vector IS NOT NULL
             AND wle.search_vector @@ q.tsq
            THEN ts_headline(
                'english',
                COALESCE(wle.title, '') || ' ' || COALESCE(wle.description, '') || ' ' || COALESCE(wle.summary, ''),
                q.tsq,
                'MaxWords=35,MinWords=10,MaxFragments=3'
            )
            ELSE LEFT(COALESCE(wle.summary, COALESCE(wle.description, COALESCE(wle.title, ''))), 220)
        END                                                                          AS snippet,
        'work_log'                                                                   AS result_type,
        wle.title                                                                    AS work_log_title,
        wle.work_date::text                                                          AS work_log_date,
        NULL::text                                                                   AS turn_body_preview,
        cs.started_at                                                                AS session_started_at,
        COALESCE(cs.status, 'legacy_work_log')                                       AS session_status
    FROM work_log_entries wle
    LEFT JOIN conversation_sessions cs ON cs.id = wle.conversation_id
    CROSS JOIN q
    WHERE wle.org_id = :org_id
      AND (
          (wle.search_vector IS NOT NULL AND wle.search_vector @@ q.tsq)
          OR GREATEST(
              similarity(COALESCE(wle.title, ''), :query),
              similarity(COALESCE(wle.description, ''), :query),
              similarity(COALESCE(wle.summary, ''), :query),
              similarity(COALESCE(wle.project, ''), :query),
              similarity(COALESCE(wle.site, ''), :query),
              similarity(COALESCE(wle.location_label, ''), :query),
              similarity(COALESCE(wle.category, ''), :query)
          ) > 0.1
      )
      AND (:search_closed OR cs.id IS NULL OR cs.status = 'active')
      AND (CAST(:user_id AS UUID) IS NULL OR COALESCE(cs.user_id, wle.user_id) = CAST(:user_id AS UUID))
),
turn_matches AS (
    SELECT
        ct.id                                                                        AS source_id,
        cs.id                                                                        AS session_id,
        CASE
            WHEN ct.search_vector IS NOT NULL
             AND ct.search_vector @@ q.tsq
            THEN 0.7 * ts_rank_cd(ct.search_vector, q.tsq)
            ELSE 0.0
        END
        + 0.3 * similarity(COALESCE(ct.body_text, ''), :query)                       AS score,
        LEFT(COALESCE(ct.body_text, ''), 220)                                         AS snippet,
        'turn'                                                                        AS result_type,
        NULL::text                                                                    AS work_log_title,
        NULL::text                                                                    AS work_log_date,
        LEFT(COALESCE(ct.body_text, ''), 220)                                         AS turn_body_preview,
        cs.started_at                                                                 AS session_started_at,
        cs.status                                                                     AS session_status
    FROM conversation_turns ct
    JOIN conversation_sessions cs ON cs.id = ct.conversation_id
    CROSS JOIN q
    WHERE cs.org_id = :org_id
      AND ct.direction = 'inbound'
      AND (
          (ct.search_vector IS NOT NULL AND ct.search_vector @@ q.tsq)
          OR similarity(COALESCE(ct.body_text, ''), :query) > 0.1
      )
      AND (:search_closed OR cs.status = 'active')
      AND (CAST(:user_id AS UUID) IS NULL OR cs.user_id = CAST(:user_id AS UUID))
),
session_matches AS (
    SELECT
        cs.id                                                                        AS source_id,
        cs.id                                                                        AS session_id,
        0.3 * similarity(COALESCE(cs.title, ''), :query)                              AS score,
        LEFT(COALESCE(cs.title, ''), 220)                                              AS snippet,
        'session'                                                                      AS result_type,
        NULL::text                                                                     AS work_log_title,
        NULL::text                                                                     AS work_log_date,
        NULL::text                                                                     AS turn_body_preview,
        cs.started_at                                                                  AS session_started_at,
        cs.status                                                                      AS session_status
    FROM conversation_sessions cs
    WHERE cs.org_id = :org_id
      AND similarity(COALESCE(cs.title, ''), :query) > 0.1
      AND (:search_closed OR cs.status = 'active')
      AND (CAST(:user_id AS UUID) IS NULL OR cs.user_id = CAST(:user_id AS UUID))
)
SELECT *
FROM (
    SELECT * FROM work_log_matches
    UNION ALL
    SELECT * FROM turn_matches
    UNION ALL
    SELECT * FROM session_matches
) matches
ORDER BY score DESC, session_started_at DESC NULLS LAST
LIMIT :limit
"""


@dataclass(frozen=True)
class SearchResult:
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

    @property
    def display_title(self) -> str:
        if self.result_type == "work_log":
            return self.work_log_title or "Untitled work log"
        if self.result_type == "turn":
            return (self.turn_body_preview or self.snippet or "Conversation turn")[:80]
        return self.snippet or "Conversation session"

    @property
    def display_date(self) -> str:
        if self.work_log_date:
            return self.work_log_date
        if self.session_started_at is not None:
            return self.session_started_at.isoformat()
        return "Unknown"


class SessionSearcher:
    """Hybrid search across sessions, work logs, and turns."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def search(
        self,
        *,
        query: str,
        org_id: UUID,
        user_id: UUID | None = None,
        limit: int = 10,
        search_closed_sessions: bool = True,
    ) -> list[SearchResult]:
        if not query or not query.strip() or limit <= 0:
            return []

        if self._is_postgres():
            try:
                rows = (
                    self.session.execute(
                        text(_HYBRID_SEARCH_SQL),
                        {
                            "query": query.strip(),
                            "org_id": org_id,
                            "user_id": user_id,
                            "limit": limit,
                            "search_closed": search_closed_sessions,
                        },
                    )
                    .mappings()
                    .all()
                )
                return [self._row_to_result(row) for row in rows]
            except SQLAlchemyError:
                logger.warning("Hybrid session search failed, falling back to LIKE search", exc_info=True)
                self.session.rollback()

        return self._fallback_search(
            query=query,
            org_id=org_id,
            user_id=user_id,
            limit=limit,
            search_closed_sessions=search_closed_sessions,
        )

    def search_work_log_entries(
        self,
        *,
        query: str | None,
        org_id: UUID,
        user_id: UUID | None = None,
        limit: int = 25,
        confirmed_only: bool = True,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[WorkLogEntry]:
        """Retrieve concrete work-log rows for downstream report generation.

        This is intentionally conservative and portable. It applies org/user/date
        scoping first, then a broad text match when a query is supplied.
        """
        stmt = select(WorkLogEntry).where(WorkLogEntry.org_id == org_id)
        if user_id is not None:
            stmt = stmt.where(WorkLogEntry.user_id == user_id)
        if confirmed_only:
            stmt = stmt.where(WorkLogEntry.confirmation_status == "confirmed")
        if start_date is not None:
            stmt = stmt.where(WorkLogEntry.work_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(WorkLogEntry.work_date <= end_date)

        cleaned = (query or "").strip()
        if cleaned:
            patterns = self._patterns(cleaned)
            stmt = stmt.where(
                or_(
                    self._like_clause(WorkLogEntry.title, patterns),
                    self._like_clause(WorkLogEntry.summary, patterns),
                    self._like_clause(WorkLogEntry.description, patterns),
                    self._like_clause(WorkLogEntry.project, patterns),
                    self._like_clause(WorkLogEntry.site, patterns),
                    self._like_clause(WorkLogEntry.location_label, patterns),
                    self._like_clause(WorkLogEntry.category, patterns),
                )
            )

        stmt = (
            stmt.order_by(WorkLogEntry.work_date.desc(), WorkLogEntry.updated_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def _is_postgres(self) -> bool:
        try:
            return self.session.bind is not None and self.session.bind.dialect.name == "postgresql"
        except Exception:
            return False

    def _fallback_search(
        self,
        *,
        query: str,
        org_id: UUID,
        user_id: UUID | None,
        limit: int,
        search_closed_sessions: bool,
    ) -> list[SearchResult]:
        cleaned = query.strip()
        patterns = self._patterns(cleaned)
        results: list[SearchResult] = []

        work_log_stmt = (
            select(WorkLogEntry, ConversationSession)
            .outerjoin(ConversationSession, ConversationSession.id == WorkLogEntry.conversation_id)
            .where(
                WorkLogEntry.org_id == org_id,
                or_(
                    self._like_clause(WorkLogEntry.title, patterns),
                    self._like_clause(WorkLogEntry.summary, patterns),
                    self._like_clause(WorkLogEntry.description, patterns),
                    self._like_clause(WorkLogEntry.project, patterns),
                    self._like_clause(WorkLogEntry.site, patterns),
                    self._like_clause(WorkLogEntry.location_label, patterns),
                    self._like_clause(WorkLogEntry.category, patterns),
                ),
            )
            .order_by(WorkLogEntry.work_date.desc(), WorkLogEntry.updated_at.desc())
            .limit(limit)
        )
        if user_id is not None:
            work_log_stmt = work_log_stmt.where(WorkLogEntry.user_id == user_id)
        if not search_closed_sessions:
            work_log_stmt = work_log_stmt.where(
                or_(
                    ConversationSession.id.is_(None),
                    ConversationSession.status == "active",
                )
            )

        for entry, session in self.session.execute(work_log_stmt).all():
            results.append(
                SearchResult(
                    source_id=str(entry.id),
                    session_id=str((session.id if session is not None else entry.conversation_id) or entry.id),
                    score=self._python_score(
                        cleaned,
                        [
                            entry.title,
                            entry.summary,
                            entry.description,
                            entry.project,
                            entry.site,
                            entry.location_label,
                            entry.category,
                        ],
                    ),
                    snippet=(entry.summary or entry.description or entry.title or "")[:220],
                    result_type="work_log",
                    work_log_title=entry.title,
                    work_log_date=entry.work_date.isoformat() if entry.work_date else None,
                    session_started_at=session.started_at if session is not None else None,
                    session_status=session.status if session is not None else "legacy_work_log",
                )
            )

        turn_stmt = (
            select(ConversationTurn, ConversationSession)
            .join(ConversationSession, ConversationSession.id == ConversationTurn.conversation_id)
            .where(
                ConversationSession.org_id == org_id,
                ConversationTurn.direction == "inbound",
                self._like_clause(ConversationTurn.body_text, patterns),
            )
            .order_by(ConversationTurn.occurred_at.desc())
            .limit(limit)
        )
        if user_id is not None:
            turn_stmt = turn_stmt.where(ConversationSession.user_id == user_id)
        if not search_closed_sessions:
            turn_stmt = turn_stmt.where(ConversationSession.status == "active")

        for turn, session in self.session.execute(turn_stmt).all():
            body = turn.body_text or ""
            preview = body[:220]
            results.append(
                SearchResult(
                    source_id=str(turn.id),
                    session_id=str(session.id),
                    score=self._python_score(cleaned, [body]),
                    snippet=preview,
                    result_type="turn",
                    turn_body_preview=preview,
                    session_started_at=session.started_at,
                    session_status=session.status,
                )
            )

        session_stmt = (
            select(ConversationSession)
            .where(
                ConversationSession.org_id == org_id,
                self._like_clause(ConversationSession.title, patterns),
            )
            .order_by(ConversationSession.started_at.desc())
            .limit(limit)
        )
        if user_id is not None:
            session_stmt = session_stmt.where(ConversationSession.user_id == user_id)
        if not search_closed_sessions:
            session_stmt = session_stmt.where(ConversationSession.status == "active")

        for session in self.session.scalars(session_stmt):
            results.append(
                SearchResult(
                    source_id=str(session.id),
                    session_id=str(session.id),
                    score=self._python_score(cleaned, [session.title or ""]),
                    snippet=(session.title or "Conversation session")[:220],
                    result_type="session",
                    session_started_at=session.started_at,
                    session_status=session.status,
                )
            )

        results.sort(key=lambda item: (item.score, item.session_started_at or datetime.min), reverse=True)
        return results[:limit]

    def _row_to_result(self, row: Any) -> SearchResult:
        return SearchResult(
            source_id=str(row["source_id"]),
            session_id=str(row["session_id"]),
            score=float(row["score"] or 0.0),
            snippet=str(row["snippet"] or ""),
            result_type=str(row["result_type"]),
            work_log_title=(str(row["work_log_title"]) if row.get("work_log_title") else None),
            work_log_date=(str(row["work_log_date"]) if row.get("work_log_date") else None),
            turn_body_preview=(
                str(row["turn_body_preview"]) if row.get("turn_body_preview") else None
            ),
            session_started_at=row.get("session_started_at"),
            session_status=(str(row["session_status"]) if row.get("session_status") else None),
        )

    def _patterns(self, query: str) -> list[str]:
        cleaned = query.strip()
        if not cleaned:
            return []
        stopwords = {
            "a",
            "an",
            "and",
            "details",
            "for",
            "from",
            "last",
            "make",
            "need",
            "next",
            "report",
            "that",
            "the",
            "this",
            "use",
            "week",
            "with",
            "yesterday",
        }
        patterns = [f"%{cleaned}%"]
        seen = {cleaned.casefold()}
        for token in cleaned.split():
            normalized = token.strip(".,:;!?()[]{}\"'").casefold()
            if len(normalized) < 3 or normalized in stopwords or normalized in seen:
                continue
            patterns.append(f"%{normalized}%")
            seen.add(normalized)
        return patterns

    def _like_clause(self, column: Any, patterns: list[str]):
        return or_(*[column.ilike(pattern) for pattern in patterns])

    def _python_score(self, query: str, values: list[str | None]) -> float:
        q = query.casefold()
        points = 0.0
        for value in values:
            text_value = (value or "").casefold()
            if not text_value:
                continue
            if q in text_value:
                points += 1.0
            elif any(token and token in text_value for token in q.split()):
                points += 0.35
        max_points = max(len(values), 1)
        return round(points / max_points, 4)
