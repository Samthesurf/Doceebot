from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from whatsapp_ai_agent.db.models import Base, Organization, User, WorkLogEntry
from whatsapp_ai_agent.memory.session_search import SessionSearcher


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
