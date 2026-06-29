def should_use_semantic_retrieval(query: str) -> bool:
    fuzzy_words = {"mention", "similar", "find", "where"}
    return any(word in query.lower() for word in fuzzy_words)
