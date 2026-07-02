from enum import StrEnum


class RetrievalRoute(StrEnum):
    SQL = "sql"
    RAG = "rag"
    HYBRID = "hybrid"


FUZZY_RAG_TERMS = {
    "mention",
    "similar",
    "find",
    "where did i mention",
    "policy",
    "manual",
    "sop",
    "procedure",
    "document",
    "template",
    "guide",
    "meaning",
}

SQL_OPERATIONAL_TERMS = {
    "today",
    "yesterday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "daily report",
    "weekly report",
    "generate",
    "append",
    "excel",
    "xlsx",
    "work log",
    "logs from",
    "status",
    "who logged",
}

HYBRID_TERMS = {
    "compare",
    "according to policy",
    "against policy",
    "with policy",
    "safety issues",
    "blockers recurring",
}


def classify_retrieval_route(query: str) -> RetrievalRoute:
    lowered = query.lower()
    if any(term in lowered for term in HYBRID_TERMS):
        return RetrievalRoute.HYBRID

    has_sql = any(term in lowered for term in SQL_OPERATIONAL_TERMS)
    has_rag = any(term in lowered for term in FUZZY_RAG_TERMS)
    if has_sql and has_rag:
        return RetrievalRoute.HYBRID
    if has_rag:
        return RetrievalRoute.RAG
    return RetrievalRoute.SQL


def should_use_semantic_retrieval(query: str) -> bool:
    return classify_retrieval_route(query) in {RetrievalRoute.RAG, RetrievalRoute.HYBRID}
