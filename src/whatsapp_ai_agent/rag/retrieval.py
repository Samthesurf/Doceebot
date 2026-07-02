from typing import Any

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.core.permissions import Role, Visibility
from whatsapp_ai_agent.rag.cloudflare_client import CloudflareAIClient
from whatsapp_ai_agent.rag.schemas import MetadataValue, RagSearchResult

ROLE_ALLOWED_VISIBILITIES: dict[Role, set[str]] = {
    Role.WORKER: {Visibility.WORKER_VISIBLE.value},
    Role.SUPERVISOR: {Visibility.WORKER_VISIBLE.value, Visibility.SUPERVISOR_SUMMARY.value},
    Role.MANAGER: {
        Visibility.WORKER_VISIBLE.value,
        Visibility.SUPERVISOR_SUMMARY.value,
        Visibility.MANAGEMENT.value,
    },
    Role.ORG_ADMIN: {
        Visibility.WORKER_VISIBLE.value,
        Visibility.SUPERVISOR_SUMMARY.value,
        Visibility.MANAGEMENT.value,
    },
}


def allowed_visibilities_for_role(role: Role) -> set[str]:
    return set(ROLE_ALLOWED_VISIBILITIES[role])


def build_ai_search_filters(
    *,
    org_id: str,
    role: Role,
    source_types: list[str] | None = None,
    visibilities: list[str] | None = None,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    """Build Cloudflare AI Search filters with tenant and role scoping.

    These filters are a first line of defense. Results are still post-filtered
    after Cloudflare returns chunks because the backend, not the model or RAG
    provider, is the security boundary.
    """

    allowed = allowed_visibilities_for_role(role)
    if visibilities is not None:
        allowed &= set(visibilities)

    filters: dict[str, Any] = {"org_id": org_id}
    if allowed:
        filters["visibility"] = (
            sorted(allowed)[0] if len(allowed) == 1 else {"$in": sorted(allowed)}
        )
    else:
        filters["visibility"] = "__no_allowed_visibility__"

    if source_types:
        filters["source_type"] = (
            source_types[0] if len(source_types) == 1 else {"$in": sorted(set(source_types))}
        )
    if owner_user_id:
        filters["owner_user_id"] = owner_user_id
    return filters


def instance_id_for_org(settings: Settings, org_id: str) -> str:
    if settings.cloudflare_ai_search_instance:
        return settings.cloudflare_ai_search_instance
    safe_org = org_id.lower().replace("_", "-")
    return f"{settings.cloudflare_ai_search_instance_prefix}-{safe_org}"


def _metadata_from_chunk(chunk: dict[str, Any]) -> dict[str, MetadataValue]:
    raw_item = chunk.get("item")
    item: dict[str, Any] = raw_item if isinstance(raw_item, dict) else {}
    raw_metadata = item.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    raw_attributes = chunk.get("attributes")
    attributes: dict[str, Any] = raw_attributes if isinstance(raw_attributes, dict) else {}
    raw_file_attrs = attributes.get("file")
    file_attrs: dict[str, Any] = raw_file_attrs if isinstance(raw_file_attrs, dict) else {}

    merged: dict[str, MetadataValue] = {}
    for source in (metadata, file_attrs):
        for key, value in source.items():
            if isinstance(value, str | int | float | bool):
                merged[key] = value
    return merged


def parse_ai_search_chunk(chunk: dict[str, Any]) -> RagSearchResult:
    metadata = _metadata_from_chunk(chunk)
    raw_item = chunk.get("item")
    item: dict[str, Any] = raw_item if isinstance(raw_item, dict) else {}
    raw_text = chunk.get("text")
    text = raw_text if isinstance(raw_text, str) else ""
    raw_score = chunk.get("score")
    score = raw_score if isinstance(raw_score, int | float) else None
    raw_item_key = item.get("key")
    item_key = raw_item_key if isinstance(raw_item_key, str) else None
    return RagSearchResult(
        org_id=str(metadata.get("org_id") or ""),
        document_id=str(metadata.get("document_id") or item_key or "") or None,
        source_type=str(metadata.get("source_type") or "") or None,
        visibility=str(metadata.get("visibility") or "") or None,
        text=text,
        score=float(score) if score is not None else None,
        item_key=item_key,
        metadata=metadata,
    )


def result_allowed_for_request(result: RagSearchResult, *, org_id: str, role: Role) -> bool:
    return result.org_id == org_id and result.visibility in allowed_visibilities_for_role(role)


async def retrieve_org_documents(
    *,
    org_id: str,
    query: str,
    role: Role = Role.WORKER,
    user_id: str | None = None,
    source_types: list[str] | None = None,
    visibilities: list[str] | None = None,
    client: CloudflareAIClient | None = None,
    settings: Settings | None = None,
) -> list[RagSearchResult]:
    """Query Cloudflare AI Search with mandatory org and role filters."""

    settings = settings or get_settings()
    instance_id = instance_id_for_org(settings, org_id)
    filters = build_ai_search_filters(
        org_id=org_id,
        role=role,
        source_types=source_types,
        visibilities=visibilities,
        owner_user_id=user_id if visibilities == [Visibility.PRIVATE.value] else None,
    )

    owns_client = client is None
    client = client or CloudflareAIClient(settings=settings)
    try:
        chunks = await client.search_ai_search_instance(
            instance_id,
            namespace=settings.cloudflare_ai_search_namespace,
            query=query,
            filters=filters,
            max_results=settings.cloudflare_ai_search_max_results,
        )
    finally:
        if owns_client:
            await client.aclose()

    results = [parse_ai_search_chunk(chunk) for chunk in chunks]
    return [
        result for result in results if result_allowed_for_request(result, org_id=org_id, role=role)
    ]
