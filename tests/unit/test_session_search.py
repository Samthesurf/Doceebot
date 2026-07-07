from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from whatsapp_ai_agent.db.models import Base, Organization, User, WorkLogEntry
from whatsapp_ai_agent.memory.session_search import (
    _HYBRID_SEARCH_SQL,
    SearchResult,
    SessionSearcher,
)


def test_session_search_includes_legacy_work_logs_without_conversation_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    org_id = uuid4()
    user_id = uuid4()
    now = datetime.now(UTC)

    with Session() as session:
        session.add(Organization(id=org_id, name="Legacy Org", created_at=now))
        session.add(
            User(
                id=user_id,
                display_name="Legacy User",
                phone_number="+15550001111",
                created_at=now,
            )
        )
        session.add(
            WorkLogEntry(
                org_id=org_id,
                user_id=user_id,
                conversation_id=None,
                work_date=date(2026, 7, 1),
                title="Legacy transformer inspection",
                description="Checked oil level and terminal tightness",
                summary="Legacy transformer inspection",
                confirmation_status="confirmed",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

        results = SessionSearcher(session).search(
            query="transformer details from last week",
            org_id=org_id,
            user_id=user_id,
            limit=5,
        )

        assert results
        assert results[0].result_type == "work_log"
        assert results[0].work_log_title == "Legacy transformer inspection"
        assert results[0].session_status == "legacy_work_log"


def test_hybrid_search_sql_casts_nullable_user_id_to_uuid():
    assert "CAST(:user_id AS UUID) IS NULL" in _HYBRID_SEARCH_SQL


def test_session_search_rolls_back_before_fallback_when_hybrid_query_fails():
    class DummySession:
        def __init__(self) -> None:
            self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
            self.rollback_called = False

        def execute(self, *_args, **_kwargs):
            raise SQLAlchemyError("boom")

        def rollback(self) -> None:
            self.rollback_called = True

    dummy_session = DummySession()
    searcher = SessionSearcher(dummy_session)  # type: ignore[arg-type]
    expected = [
        SearchResult(
            source_id="1",
            session_id="1",
            score=1.0,
            snippet="fallback result",
            result_type="session",
        )
    ]

    def fake_fallback(**_kwargs):
        assert dummy_session.rollback_called is True
        return expected

    searcher._fallback_search = fake_fallback  # type: ignore[method-assign]

    results = searcher.search(query="oron", org_id=uuid4(), user_id=None, limit=10)

    assert dummy_session.rollback_called is True
    assert results == expected
