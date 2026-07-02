import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.permissions import Role, Visibility
from whatsapp_ai_agent.rag.indexing import (
    assert_indexable,
    build_ai_search_metadata,
    build_org_r2_key,
    prepare_text_item,
)
from whatsapp_ai_agent.rag.retrieval import (
    build_ai_search_filters,
    parse_ai_search_chunk,
    retrieve_org_documents,
)
from whatsapp_ai_agent.rag.schemas import RagDocument


def test_rag_metadata_repeats_mandatory_tenant_fields():
    document = RagDocument(
        org_id="org-1",
        document_id="doc-1",
        source_type="company_document",
        visibility=Visibility.WORKER_VISIBLE.value,
        text="Approved safety policy text",
        owner_user_id="user-1",
    )

    metadata = build_ai_search_metadata(document)

    assert metadata == {
        "org_id": "org-1",
        "source_type": "company_document",
        "visibility": "worker_visible",
        "document_id": "doc-1",
        "owner_user_id": "user-1",
    }


def test_raw_internal_artifacts_are_not_indexable():
    document = RagDocument(
        org_id="org-1",
        source_type="transcript",
        visibility=Visibility.SUPERVISOR_SUMMARY.value,
        text="Raw private transcript",
    )

    with pytest.raises(ValueError, match="must not be indexed"):
        assert_indexable(document)


def test_prepare_text_item_requires_approved_sanitized_source():
    document = RagDocument(
        org_id="org-1",
        source_type="daily_summary",
        visibility=Visibility.SUPERVISOR_SUMMARY.value,
        text="Sanitized summary for dashboard and retrieval.",
    )

    body, metadata = prepare_text_item(document)

    assert body == b"Sanitized summary for dashboard and retrieval."
    assert metadata["org_id"] == "org-1"
    assert metadata["source_type"] == "daily_summary"
    assert metadata["visibility"] == "supervisor_summary"
    assert metadata["document_id"]


def test_org_r2_key_is_tenant_prefixed():
    document = RagDocument(
        org_id="Org 1",
        source_type="company_document",
        visibility=Visibility.WORKER_VISIBLE.value,
        text="Manual text",
        document_id="manual-1",
    )

    assert build_org_r2_key(document, filename="Safety Manual.pdf") == (
        "orgs/Org-1/rag/company_document/Safety-Manual.pdf"
    )


def test_ai_search_filters_always_include_org_and_role_visibility():
    filters = build_ai_search_filters(
        org_id="org-1",
        role=Role.SUPERVISOR,
        source_types=["daily_summary", "weekly_summary"],
    )

    assert filters["org_id"] == "org-1"
    assert filters["visibility"] == {"$in": ["supervisor_summary", "worker_visible"]}
    assert filters["source_type"] == {"$in": ["daily_summary", "weekly_summary"]}


def test_parse_and_post_filter_ai_search_chunks():
    chunk = {
        "text": "Summary text",
        "score": 0.91,
        "item": {
            "key": "summary.md",
            "metadata": {
                "org_id": "org-1",
                "document_id": "doc-1",
                "source_type": "daily_summary",
                "visibility": "supervisor_summary",
            },
        },
    }

    result = parse_ai_search_chunk(chunk)

    assert result.org_id == "org-1"
    assert result.document_id == "doc-1"
    assert result.source_type == "daily_summary"
    assert result.visibility == "supervisor_summary"
    assert result.text == "Summary text"
    assert result.score == 0.91


@pytest.mark.asyncio
async def test_retrieve_org_documents_sends_scoped_query_and_drops_wrong_org():
    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        async def search_ai_search_instance(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return [
                {
                    "text": "Allowed result",
                    "item": {
                        "key": "allowed.md",
                        "metadata": {
                            "org_id": "org-1",
                            "document_id": "doc-1",
                            "source_type": "company_document",
                            "visibility": "worker_visible",
                        },
                    },
                },
                {
                    "text": "Wrong tenant leak attempt",
                    "item": {
                        "key": "blocked.md",
                        "metadata": {
                            "org_id": "org-2",
                            "document_id": "doc-2",
                            "source_type": "company_document",
                            "visibility": "worker_visible",
                        },
                    },
                },
            ]

    fake = FakeClient()
    settings = Settings(
        cloudflare_ai_search_instance="shared-doceebot",
        cloudflare_ai_search_max_results=3,
        _env_file=None,
    )

    results = await retrieve_org_documents(
        org_id="org-1",
        query="find safety policy",
        role=Role.WORKER,
        client=fake,
        settings=settings,
    )

    assert [result.text for result in results] == ["Allowed result"]
    args, kwargs = fake.calls[0]
    assert args == ("shared-doceebot",)
    assert kwargs["filters"] == {"org_id": "org-1", "visibility": "worker_visible"}
    assert kwargs["max_results"] == 3
