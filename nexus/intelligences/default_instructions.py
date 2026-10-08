"""Read-only default instructions for the Agent Builder.

The texts ship in ``default_project_instructions.json``, next to this module.
The image copies the application directory, so the file is included without a
package-data setting. ``DEFAULT_PROJECT_INSTRUCTIONS_FILE`` can point at
another JSON file, usually a ConfigMap mount, with the same shape: an object
whose keys are language codes (``pt``, ``en``, ``es``, ``ro``) and whose
values are lists of instruction strings. A missing, unreadable, or invalid
file keeps the copy that ships with the image.

This catalog is what the instruction list and the CSV export show. It is not
``DEFAULT_INSTRUCTIONS``, the legacy prompt used only when a content base has
no stored instructions. These instructions are not stored on the project.
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
_CACHE_LIMIT = 8
_catalog_cache: dict[tuple[str, tuple[int, int] | None], dict[str, list[str]] | None] = {}
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


class DefaultInstructionCatalogError(RuntimeError):
    """The catalog shipped with the image cannot be loaded."""


def clear_catalog_cache() -> None:
    _catalog_cache.clear()


def language_code(language: str | None, *, fallback: str | None = _FALLBACK_LANGUAGE) -> str | None:
    normalized = (language or "").strip().casefold().replace("_", "-")
    if not normalized:
        return fallback
    if normalized in _LANGUAGE_CODES:
        return _LANGUAGE_CODES[normalized]
    primary = normalized.split("-", 1)[0]
    return _LANGUAGE_CODES.get(primary, fallback)


def default_instruction_texts(language: str | None = "Portuguese") -> list[str]:
    code = language_code(language) or _FALLBACK_LANGUAGE
    override = _catalog_from_path(getattr(settings, "DEFAULT_PROJECT_INSTRUCTIONS_FILE", ""))
    if override and code in override:
        return override[code]

    packaged = _catalog_from_path(_PACKAGED_CATALOG)
    if not packaged:
        raise DefaultInstructionCatalogError(
            f"Packaged default instruction catalog is missing or invalid: {_PACKAGED_CATALOG}"
        )
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

    file_path = Path(location)
    key = (location, _file_stamp(file_path))
    if key in _catalog_cache:
        return _catalog_cache[key]

    catalog = _read_catalog(file_path, location)
    if len(_catalog_cache) >= _CACHE_LIMIT:
        _catalog_cache.clear()
    _catalog_cache[key] = catalog
    return catalog


def _file_stamp(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _read_catalog(path: Path, location: str) -> dict[str, list[str]] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
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
