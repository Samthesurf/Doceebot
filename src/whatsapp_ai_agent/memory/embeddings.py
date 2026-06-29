def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]
