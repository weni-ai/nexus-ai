WEBCHAT_CHANNEL_TYPES = frozenset({"WWC", "WEBCHAT", "WEB_CHAT"})


def is_webchat_channel(contact_urn: str, channel_type: str = "") -> bool:
    if (channel_type or "").strip().upper() in WEBCHAT_CHANNEL_TYPES:
        return True
    lower = (contact_urn or "").lower()
    return lower.startswith("ext:") or "webchat" in lower


def channel_hint_from_contact_urn(contact_urn: str, channel_type: str = "") -> str:
    """Log label: web for webchat channels, otherwise the URN prefix."""
    if is_webchat_channel(contact_urn, channel_type):
        return "web"
    if not contact_urn:
        return "unknown"
    prefix, _, _ = contact_urn.partition(":")
    return prefix or "unknown"


def supports_progressive_feedback(
    contact_urn: str,
    channel_type: str = "",
    *,
    preview: bool = False,
    preview_websocket: bool = False,
) -> bool:
    if preview or preview_websocket:
        return True
    return is_webchat_channel(contact_urn, channel_type)
