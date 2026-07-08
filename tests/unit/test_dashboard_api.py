from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from whatsapp_ai_agent.api.dashboard import DashboardUser, require_dashboard_user
from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.db.models import (
    Base,
    ConversationSession,
    ConversationTurn,
    DeveloperEscalation,
    ManagedDocument,
    ManagedDocumentUpdate,
    Membership,
    Organization,
    User,
    WorkLogEntry,
)
from whatsapp_ai_agent.db.session import get_db_session
from whatsapp_ai_agent.main import create_app


def _client_with_dashboard_data(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    settings = Settings(
        firebase_project_id="doceebot-test",
        dashboard_allowed_emails="admin@example.com",
        dashboard_logs_password="correct-horse-battery-staple",
        local_storage_dir=str(tmp_path),
        _env_file=None,
    )

    org_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()
    document_id = uuid4()
    now = datetime.now(UTC)
    with Session() as session:
        session.add(Organization(id=org_id, name="Milk Brown Farms", created_at=now))
        session.add(
            User(
                id=user_id,
                display_name="Ada Admin",
                email="admin@example.com",
                phone_number="+155****0001",
                created_at=now,
            )
        )
        session.add(Membership(org_id=org_id, user_id=user_id, role="admin"))

        session.add(
            ConversationSession(
                id=conversation_id,
                org_id=org_id,
                user_id=user_id,
                platform="whatsapp",
                platform_chat_id="whatsapp:+15550001",
                status="active",
                started_at=now,
                last_message_at=now,
                created_at=now,
            )
        )
        session.add(
            ConversationTurn(
                conversation_id=conversation_id,
                direction="inbound",
                platform="whatsapp",
                platform_message_id="SM123",
                message_type="text",
                body_text="worked on packaging line",
                media_json="[]",
                raw_payload_json='{"redacted": true}',
                metadata_json='{"command": "status"}',
                occurred_at=now,
                created_at=now,
            )
        )
        session.add(
            WorkLogEntry(
                conversation_id=conversation_id,
                org_id=org_id,
                user_id=user_id,
                work_date=date.today(),
                title="Packaging line maintenance",
                description="Adjusted conveyor guides",
                summary="Packaging line maintenance",
                confirmation_status="draft",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ManagedDocument(
                id=document_id,
                org_id=org_id,
                owner_user_id=user_id,
                display_name="Daily Log Template",
                filename="daily-log.xlsx",
                document_kind="xlsx_template",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                storage_backend="local",
                storage_key="managed-documents/daily-log.xlsx",
                size_bytes=2048,
                sha256_hex="a" * 64,
                source_type="upload",
                status="processed",
                summary="Template used for daily logs",
                tags_json='["daily", "template"]',
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ManagedDocumentUpdate(
                org_id=org_id,
                document_id=document_id,
                user_id=user_id,
                update_kind="upload",
                instruction="Initial upload",
                changes_json="[]",
                created_at=now,
            )
        )
        session.add(
            DeveloperEscalation(
                conversation_id=conversation_id,
                org_id=org_id,
                user_id=user_id,
                platform="whatsapp",
                report_text="Need review",
                conversation_snapshot_json='{"llm_audits_redacted": true}',
                status="pending",
                destination="dashboard",
                created_at=now,
            )
        )
        session.commit()

    def override_db_session():
        with Session() as session:
            yield session

    app = create_app(settings)
    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_dashboard_user] = lambda: DashboardUser(
        uid="test-admin",
        email="admin@example.com",
        name="Admin",
        picture=None,
    )
    return TestClient(app), org_id


def test_dashboard_me_uses_firebase_dependency_override(tmp_path):
    client, _ = _client_with_dashboard_data(tmp_path)

    response = client.get("/dashboard-api/me")

    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.com"


def test_dashboard_inventory_endpoints_return_redacted_management_views(tmp_path):
    client, _org_id = _client_with_dashboard_data(tmp_path)

    organizations = client.get("/dashboard-api/organizations")
    documents = client.get("/dashboard-api/documents")
    escalations = client.get("/dashboard-api/escalations")

    assert organizations.status_code == 200
    assert organizations.json()["organizations"][0]["name"] == "Milk Brown Farms"
    assert organizations.json()["organizations"][0]["document_count"] == 1

    assert documents.status_code == 200
    document = documents.json()["documents"][0]
    assert document["filename"] == "daily-log.xlsx"
    assert document["tags"] == ["daily", "template"]
    assert "storage_key" not in document
    assert "storage_url" not in document

    assert escalations.status_code == 200
    escalation = escalations.json()["escalations"][0]
    assert escalation["report_text"] == "Need review"
    assert escalation["turn_count"] == 1


def test_dashboard_logs_require_second_password_and_hide_raw_payloads(tmp_path):
    client, _ = _client_with_dashboard_data(tmp_path)

    assert client.get("/dashboard-api/logs").status_code == 403
    assert (
        client.get("/dashboard-api/logs", headers={"X-Logs-Password": "wrong"}).status_code
        == 403
    )

    response = client.get(
        "/dashboard-api/logs",
        headers={"X-Logs-Password": "correct-horse-battery-staple"},
    )

    assert response.status_code == 200
    conversation = response.json()["conversations"][0]
    assert conversation["organization_name"] == "Milk Brown Farms"
    assert conversation["turns"][0]["body_text"] == "worked on packaging line"
    assert conversation["turns"][0]["metadata"] == {"command": "status"}
    assert "raw_payload_json" not in conversation["turns"][0]


def test_dashboard_search_returns_hybrid_session_matches(tmp_path):
    client, org_id = _client_with_dashboard_data(tmp_path)

    response = client.get(
        "/dashboard-api/search",
        params={"q": "packaging", "org_id": str(org_id), "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "packaging"
    assert payload["org_id"] == str(org_id)
    assert payload["results"]
    assert {item["result_type"] for item in payload["results"]} >= {"work_log", "turn"}
    assert any(item["display_title"] == "Packaging line maintenance" for item in payload["results"])


def test_dashboard_admin_access_returns_linked_org_memberships(tmp_path):
    client, org_id = _client_with_dashboard_data(tmp_path)

    response = client.get("/dashboard-api/admin/access")

    assert response.status_code == 200
    payload = response.json()
    assert payload["linked_user_email"] == "admin@example.com"
    assert payload["organizations"] == [
        {
            "id": str(org_id),
            "name": "Milk Brown Farms",
            "role": "org_admin",
            "member_count": 1,
        }
    ]


def test_dashboard_admin_can_create_and_list_telegram_org_user(tmp_path):
    client, org_id = _client_with_dashboard_data(tmp_path)

    create_response = client.post(
        "/dashboard-api/admin/users",
        json={
            "org_id": str(org_id),
            "platform": "telegram",
            "identifier": "7994559684",
            "role": "worker",
            "display_name": "Telegram Tester",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["organization_name"] == "Milk Brown Farms"
    assert created["created_user"] is True
    assert created["created_membership"] is True
    assert created["updated_membership_role"] is False
    assert created["user"]["telegram_user_id"] == "7994559684"
    assert created["user"]["role"] == "worker"

    list_response = client.get("/dashboard-api/admin/users", params={"org_id": str(org_id)})

    assert list_response.status_code == 200
    members = list_response.json()["members"]
    assert any(member["telegram_user_id"] == "7994559684" for member in members)
    assert any(member["display_name"] == "Telegram Tester" for member in members)


def test_dashboard_admin_can_link_email_to_bot_user(tmp_path):
    client, org_id = _client_with_dashboard_data(tmp_path)

    create_response = client.post(
        "/dashboard-api/admin/link-email",
        json={
            "org_id": str(org_id),
            "email": "Teammate@Example.com",
            "platform": "whatsapp",
            "identifier": "+15500009999",
            "role": "org_admin",
            "display_name": "Linked Teammate",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["organization_name"] == "Milk Brown Farms"
    assert created["email"] == "teammate@example.com"
    assert created["created_user"] is True
    assert created["created_membership"] is True
    assert created["updated_membership_email"] is True
    assert created["user"]["phone_number"] == "+15500009999"
    assert created["user"]["role"] == "org_admin"

    # Use the freshly minted email as a dashboard login to confirm it is now linked.
    app = client.app
    app.dependency_overrides[require_dashboard_user] = lambda: DashboardUser(
        uid="linked-admin",
        email="teammate@example.com",
        name="Linked Teammate",
        picture=None,
    )
    access = client.get("/dashboard-api/admin/access")
    assert access.status_code == 200
    payload = access.json()
    assert payload["linked_user_email"] == "teammate@example.com"
    assert any(org["id"] == str(org_id) for org in payload["organizations"])

    # Linking the same email to a different user record must conflict.
    second = client.post(
        "/dashboard-api/admin/link-email",
        json={
            "org_id": str(org_id),
            "email": "teammate@example.com",
            "platform": "telegram",
            "identifier": "9990001112",
            "role": "worker",
        },
    )
    assert second.status_code == 409
