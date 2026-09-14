"""Whirlpool generateContent custom Model provider (PoC)."""

from inline_agents.backends.openai.custom_providers.registry import register_provider
from inline_agents.backends.openai.custom_providers.whirlpool.model import WhirlpoolModel

WHIRLPOOL_MODEL_ID = "custom/whirlpool/generateContent"

# Credential field ids expected on ModelProvider / ProjectModelProvider
WHIRLPOOL_CREDENTIAL_SCHEMA = [
    {"id": "client_id", "label": "Client ID", "type": "PASSWORD"},
    {"id": "client_secret", "label": "Client secret", "type": "PASSWORD"},
    {"id": "token_url", "label": "OAuth token URL", "type": "TEXT"},
    {"id": "generate_content_url", "label": "generateContent URL", "type": "TEXT"},
    {"id": "api_base", "label": "API base host (optional)", "type": "TEXT"},
]


def _factory(model: str, credentials: dict) -> WhirlpoolModel:
    return WhirlpoolModel(model=model or WHIRLPOOL_MODEL_ID, credentials=credentials)


register_provider("whirlpool", _factory)

__all__ = [
    "WHIRLPOOL_CREDENTIAL_SCHEMA",
    "WHIRLPOOL_MODEL_ID",
    "WhirlpoolModel",
]
