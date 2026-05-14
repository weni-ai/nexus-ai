"""Legacy OpenAI inline pipeline `2.6` helpers — isolate for easy removal."""

from __future__ import annotations

LEGACY_PIPELINE_VERSION = "2.6"

NEW_PIPELINE_SENTINEL = "new"


def normalize_pipeline_version(version: str | None) -> str | None:
    if version is None:
        return None
    s = str(version).strip()
    return s or None


def is_legacy_pipeline_version(version: str | None) -> bool:
    return normalize_pipeline_version(version) == LEGACY_PIPELINE_VERSION


def is_new_pipeline_sentinel(value: str | None) -> bool:
    """Return True when the cached value explicitly forces the non-legacy pipeline."""
    if value is None:
        return False
    return str(value).strip().lower() == NEW_PIPELINE_SENTINEL


def use_legacy_formatter_after_manager(version: str | None) -> bool:
    """Formatter LLM after manager applies only on legacy pipeline token."""
    return is_legacy_pipeline_version(version)
