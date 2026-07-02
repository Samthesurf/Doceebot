from whatsapp_ai_agent.memory.retrieval_router import RetrievalRoute, classify_retrieval_route


def test_retrieval_router_sends_date_bound_report_requests_to_sql():
    assert classify_retrieval_route("Generate today's work log report") == RetrievalRoute.SQL


def test_retrieval_router_sends_policy_and_manual_questions_to_rag():
    assert classify_retrieval_route("Find the inverter safety policy") == RetrievalRoute.RAG


def test_retrieval_router_uses_hybrid_for_records_plus_policy_questions():
    assert (
        classify_retrieval_route("Compare this week's safety issues against policy")
        == RetrievalRoute.HYBRID
    )
