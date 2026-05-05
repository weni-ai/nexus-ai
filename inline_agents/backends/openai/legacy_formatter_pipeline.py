"""Legacy OpenAI inline pipeline `2.6` helpers — isolate for easy removal."""

from __future__ import annotations

LEGACY_PIPELINE_VERSION = "2.6"


def normalize_pipeline_version(version: str | None) -> str | None:
    if version is None:
        return None
    s = str(version).strip()
    return s or None


def is_legacy_pipeline_version(version: str | None) -> bool:
    return normalize_pipeline_version(version) == LEGACY_PIPELINE_VERSION


def use_legacy_formatter_after_manager(version: str | None) -> bool:
    """Formatter LLM after manager applies only on legacy pipeline token."""
    return is_legacy_pipeline_version(version)
