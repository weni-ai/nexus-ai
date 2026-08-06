"""Registry mapping model_vendor / model prefix → custom Model factory."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from agents.models.interface import Model

logger = logging.getLogger(__name__)

ModelFactory = Callable[[str, Dict[str, Any]], Model]

_PROVIDERS: Dict[str, ModelFactory] = {}


def register_provider(vendor: str, factory: ModelFactory) -> None:
    """Register a custom model factory for a vendor key (case-insensitive)."""
    _PROVIDERS[vendor.lower()] = factory


def get_registered_vendors() -> list[str]:
    return sorted(_PROVIDERS.keys())


def _vendor_from_model_prefix(model: str) -> Optional[str]:
    """Extract vendor from ``custom/<vendor>/...`` model ids."""
    if not model or not model.startswith("custom/"):
        return None
    parts = model.split("/")
    if len(parts) >= 2 and parts[1]:
        return parts[1].lower()
    return None


def resolve_custom_model(
    model: str,
    credentials: Dict[str, Any] | None = None,
    model_vendor: str = "",
) -> Optional[Model]:
    """Return a custom Model if vendor/prefix matches a registered provider.

    Resolution order:
    1. ``model_vendor`` (e.g. ``whirlpool``)
    2. Model prefix ``custom/<vendor>/...``
    """
    _ensure_providers_loaded()
    creds = credentials or {}
    vendor = (model_vendor or "").lower().strip()
    if not vendor:
        vendor = _vendor_from_model_prefix(model) or ""

    if not vendor:
        return None

    factory = _PROVIDERS.get(vendor)
    if factory is None:
        return None

    logger.info("Resolving custom model provider vendor=%s model=%s", vendor, model)
    return factory(model, creds)


_loaded = False


def _ensure_providers_loaded() -> None:
    global _loaded
    if _loaded:
        return
    # Import side-effect: each provider module registers itself.
    from inline_agents.backends.openai.custom_providers import whirlpool  # noqa: F401

    _loaded = True
