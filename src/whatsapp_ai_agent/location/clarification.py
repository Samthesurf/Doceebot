def build_site_clarification(candidates: list[str]) -> str:
    options = "\n".join(f"{index + 1}. {name}" for index, name in enumerate(candidates))
    return f"Which location is this for?\n{options}"
