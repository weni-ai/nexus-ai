"""Read-only default instructions for the Agent Builder.

The texts ship with the image. ``DEFAULT_PROJECT_INSTRUCTIONS_FILE`` can point
at a JSON file, usually a ConfigMap mount, with the same shape: an object
whose keys are language codes (``pt``, ``en``, ``es``, ``ro``) and whose
values are lists of instruction strings. A missing, unreadable, or invalid
file keeps the copy that ships with the image. These instructions are not
stored on the project.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_PACKAGED_CATALOG = Path(__file__).with_name("default_project_instructions.json")
_FALLBACK_LANGUAGE = "pt"
_LANGUAGE_CODES = {
    "en": "en",
    "english": "en",
    "pt": "pt",
    "pt-br": "pt",
    "pt_br": "pt",
    "portuguese": "pt",
    "português": "pt",
    "es": "es",
    "spanish": "es",
    "español": "es",
    "espanol": "es",
    "ro": "ro",
    "romanian": "ro",
    "română": "ro",
}


def language_code(language: str | None, *, fallback: str | None = _FALLBACK_LANGUAGE) -> str | None:
    normalized = (language or "").strip().casefold()
    if not normalized:
        return fallback
    return _LANGUAGE_CODES.get(normalized, fallback)


def default_instruction_texts(language: str | None = "Portuguese") -> list[str]:
    code = language_code(language) or _FALLBACK_LANGUAGE
    override = _catalog_from_path(getattr(settings, "DEFAULT_PROJECT_INSTRUCTIONS_FILE", ""))
    if override and code in override:
        return override[code]

    packaged = _catalog_from_path(_PACKAGED_CATALOG)
    if not packaged:
        logger.error("Packaged default instruction catalog is missing or invalid")
        return []
    return packaged.get(code) or packaged.get(_FALLBACK_LANGUAGE) or []


def default_instruction_group(language: str | None = "Portuguese") -> dict[str, Any]:
    return {
        "editable": False,
        "deletable": False,
        "instructions": [
            {"id": f"default-{index}", "instruction": text, "locked": True}
            for index, text in enumerate(default_instruction_texts(language), start=1)
        ],
    }


def _catalog_from_path(path: str | Path | None) -> dict[str, list[str]] | None:
    location = str(path or "").strip()
    if not location:
        return None

    try:
        raw = json.loads(Path(location).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("Default instruction catalog could not be read: %s", location)
        return None

    if not isinstance(raw, dict):
        logger.warning("Default instruction catalog must be a JSON object: %s", location)
        return None

    catalog: dict[str, list[str]] = {}
    for key, value in raw.items():
        code = language_code(key, fallback=None) if isinstance(key, str) else None
        texts = _instruction_texts(value)
        if code and texts:
            catalog[code] = texts
    if not catalog:
        logger.warning("Default instruction catalog has no usable languages: %s", location)
        return None
    return catalog


def _instruction_texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
