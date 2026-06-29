from whatsapp_ai_agent.location.schemas import SiteCandidate


def resolve_site_from_text(text: str, aliases: dict[str, str]) -> SiteCandidate | None:
    lowered = text.lower()
    for alias, site_name in aliases.items():
        if alias.lower() in lowered:
            return SiteCandidate(name=site_name, confidence=0.9)
    return None
