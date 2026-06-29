def geocoding_enabled(provider: str) -> bool:
    return provider != "disabled"
