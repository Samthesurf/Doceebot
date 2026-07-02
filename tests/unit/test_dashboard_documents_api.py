from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.db.models import Base
from whatsapp_ai_agent.db.session import get_db_session
from whatsapp_ai_agent.main import create_app


def test_dashboard_upload_and_list_documents(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    settings = Settings(local_storage_dir=str(tmp_path), _env_file=None)

    def override_db_session():
        with Session() as session:
            yield session

    app = create_app(settings)
    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    org_id = uuid4()

    response = client.post(
        "/dashboard/documents/upload",
        data={
            "org_id": str(org_id),
            "display_name": "Machine X Register",
            "summary": "Uploaded Excel register for Machine X",
            "tags": "machine-x,maintenance",
        },
        files={
            "file": (
                "machine-x-register.xlsx",
                b"not a real workbook but valid upload storage bytes",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    uploaded = response.json()
    assert uploaded["filename"] == "machine-x-register.xlsx"
    assert uploaded["document_kind"] == "xlsx"
    assert uploaded["tags"] == ["machine-x", "maintenance"]

    response = client.get(
        "/dashboard/documents",
        params={"org_id": str(org_id), "query": "machine x"},
    )

    assert response.status_code == 200
    documents = response.json()["documents"]
    assert len(documents) == 1
    assert documents[0]["display_name"] == "Machine X Register"


def test_dashboard_documentation_ideas_endpoint(tmp_path):
    settings = Settings(local_storage_dir=str(tmp_path), _env_file=None)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    response = client.get("/dashboard/documentation-ideas", params={"industry": "maintenance"})

    assert response.status_code == 200
    titles = {item["title"] for item in response.json()}
    assert "Equipment maintenance log" in titles
    assert "Work order register and closeout form" in titles
