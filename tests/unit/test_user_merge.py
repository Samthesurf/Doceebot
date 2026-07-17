"""Tests for user identity merge (multi-channel history unification)."""

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from whatsapp_ai_agent.db.models import (
    Base,
    ConversationSession,
    DeveloperEscalation,
    Membership,
    Organization,
    RawInboundMessage,
    User,
    WorkLogEntry,
)
from whatsapp_ai_agent.db.users_repository import (
    UserMergeError,
    find_telegram_only_users,
    merge_users,
)


@pytest.fixture
def db_session():
    # A unique file-backed SQLite DB per test eliminates any chance of the
    # in-memory SingletonThreadPool/StaticPool sharing an in-memory database
    # across engines in the same pytest process (which corrupts UNIQUE-constraint
    # assertions). The merge logic is identical regardless of backend.
    import shutil
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="doceebot-merge-")
    db_path = Path(tmp_dir) / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as session:
        yield session
    engine.dispose()
    shutil.rmtree(tmp_dir, ignore_errors=True)


def _make_org(session, name="Org"):
    org = Organization(name=name)
    session.add(org)
    session.flush()
    return org


def _make_user(session, *, telegram=None, phone=None, email=None, name=None):
    user = User(
        display_name=name,
        email=email,
        telegram_user_id=telegram,
        phone_number=phone,
    )
    session.add(user)
    session.flush()
    return user


def _seed_history(session, user, org, *, logs=2, conversations=1, messages=1):
    conv = ConversationSession(
        org_id=org.id,
        user_id=user.id,
        platform="telegram",
        platform_chat_id="chat",
        status="active",
    )
    session.add(conv)
    session.flush()
    for _i in range(logs):
        session.add(
            WorkLogEntry(
                conversation_id=conv.id,
                org_id=org.id,
                user_id=user.id,
                work_date=date(2026, 7, 1),
                title=f"Log {_i}",
                description="d",
                summary="s",
            )
        )
    for _i in range(messages):
        session.add(
            RawInboundMessage(
                conversation_id=conv.id,
                org_id=org.id,
                user_id=user.id,
                platform="telegram",
                platform_message_id=f"raw-{uuid4().hex[:8]}",
                message_type="text",
                body_text="hi",
                received_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                raw_payload_json="{}",
            )
        )
    session.add(
        DeveloperEscalation(
            conversation_id=conv.id,
            org_id=org.id,
            user_id=user.id,
            platform="telegram",
        )
    )
    session.flush()
    return conv


def test_merge_moves_all_child_records_and_deletes_source(db_session):
    org = _make_org(db_session)
    source = _make_user(db_session, telegram="111", name="Source TG")
    target = _make_user(db_session, phone="+2348020000000", name="Target WA")
    for u in (source, target):
        db_session.add(Membership(org_id=org.id, user_id=u.id, role="worker"))
    db_session.flush()
    _seed_history(db_session, source, org, logs=3, conversations=1, messages=2)

    result = merge_users(
        db_session,
        source_user_id=source.id,
        target_user_id=target.id,
    )
    db_session.commit()

    assert result.work_logs_moved == 3
    assert result.conversations_moved == 1
    assert result.raw_messages_moved == 2
    assert result.escalations_moved == 1
    assert result.memberships_moved == 1

    # Source row gone.
    assert db_session.get(User, source.id) is None
    # Target keeps both identifiers.
    target = db_session.get(User, target.id)
    assert target.telegram_user_id == "111"
    assert target.phone_number == "+2348020000000"

    # Child records now belong to target.
    assert (
        db_session.scalar(
            select(func.count(WorkLogEntry.id)).where(WorkLogEntry.user_id == target.id)
        )
        == 3
    )
    assert (
        db_session.scalar(
            select(func.count(WorkLogEntry.id)).where(WorkLogEntry.user_id == source.id)
        )
        == 0
    )


def test_merge_preserves_source_email_when_target_missing(db_session):
    org = _make_org(db_session)
    source = _make_user(db_session, telegram="222", email="a@b.com")
    target = _make_user(db_session, phone="+2348020000001")
    for u in (source, target):
        db_session.add(Membership(org_id=org.id, user_id=u.id, role="worker"))
    db_session.flush()

    merge_users(db_session, source_user_id=source.id, target_user_id=target.id)
    db_session.commit()
    target = db_session.get(User, target.id)
    assert target.email == "a@b.com"


def test_merge_refuses_cross_org_by_default(db_session):
    org_a = _make_org(db_session, "A")
    org_b = _make_org(db_session, "B")
    source = _make_user(db_session, telegram="333")
    target = _make_user(db_session, telegram="444")
    db_session.add(Membership(org_id=org_a.id, user_id=source.id, role="worker"))
    db_session.add(Membership(org_id=org_b.id, user_id=target.id, role="worker"))
    db_session.flush()

    with pytest.raises(UserMergeError):
        merge_users(db_session, source_user_id=source.id, target_user_id=target.id)


def test_merge_allows_cross_org_when_flagged(db_session):
    org_a = _make_org(db_session, "A")
    org_b = _make_org(db_session, "B")
    source = _make_user(db_session, telegram="333")
    target = _make_user(db_session, telegram="444")
    db_session.add(Membership(org_id=org_a.id, user_id=source.id, role="worker"))
    db_session.add(Membership(org_id=org_b.id, user_id=target.id, role="worker"))
    db_session.flush()

    result = merge_users(
        db_session,
        source_user_id=source.id,
        target_user_id=target.id,
        allow_cross_org=True,
    )
    assert result.target_user_id == target.id


def test_merge_refuses_same_user(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session, telegram="555")
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="worker"))
    db_session.flush()
    with pytest.raises(UserMergeError):
        merge_users(db_session, source_user_id=user.id, target_user_id=user.id)


def test_merge_refuses_missing_user(db_session):
    org = _make_org(db_session)
    user = _make_user(db_session, telegram="666")
    db_session.add(Membership(org_id=org.id, user_id=user.id, role="worker"))
    db_session.flush()
    with pytest.raises(UserMergeError):
        merge_users(db_session, source_user_id=user.id, target_user_id=uuid4())


def test_find_telegram_only_users(db_session):
    org = _make_org(db_session)
    tg_only = _make_user(db_session, telegram="777")
    both = _make_user(db_session, telegram="888", phone="+2348020000002")
    db_session.add(Membership(org_id=org.id, user_id=tg_only.id, role="worker"))
    db_session.add(Membership(org_id=org.id, user_id=both.id, role="worker"))
    db_session.flush()

    found = find_telegram_only_users(db_session)
    ids = {u.id for u in found}
    assert tg_only.id in ids
    assert both.id not in ids


