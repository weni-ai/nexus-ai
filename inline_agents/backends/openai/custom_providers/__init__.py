"""Pluggable in-process custom Model providers for client-specific LLM APIs.

Register new clients under this package and wire them in ``registry.py``.
Selection happens in ``AgentModel.get_model`` by ``model_vendor`` or
``custom/<vendor>/...`` model prefix — ``start_inline_agents`` stays unchanged.
"""

from inline_agents.backends.openai.custom_providers.registry import (
    resolve_custom_model,
)

__all__ = ["resolve_custom_model"]
