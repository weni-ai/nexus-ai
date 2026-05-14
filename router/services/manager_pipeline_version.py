"""Resolve the inline-agent pipeline version from the project's ManagerAgent UUID.

The pipeline version is a behavior toggle (legacy formatter-after-manager vs. new
component pipeline). To keep the decision out of admin-editable JSON, the source of
truth is ``settings.LEGACY_MANAGER_AGENT_UUIDS``: an ops-controlled list of
``ManagerAgent.uuid`` values that must run the legacy code path.

The helpers below still return the legacy string token (``"2.6"``) so all existing
downstream gating in ``inline_agents.backends.openai`` keeps working unchanged.
"""

from __future__ import annotations

from typing import Iterable, Optional

from django.conf import settings

from inline_agents.backends.openai.legacy_formatter_pipeline import LEGACY_PIPELINE_VERSION


def _legacy_uuid_set() -> set[str]:
    raw: Iterable = getattr(settings, "LEGACY_MANAGER_AGENT_UUIDS", None) or []
    return {str(u).strip().lower() for u in raw if u}


def is_legacy_manager_uuid(manager_uuid) -> bool:
    """Return True when ``manager_uuid`` is configured as a legacy ManagerAgent."""
    if manager_uuid is None:
        return False
    return str(manager_uuid).strip().lower() in _legacy_uuid_set()


def manager_pipeline_version_from_project(project) -> Optional[str]:
    """Return the legacy pipeline token when the project's ManagerAgent UUID is in
    ``settings.LEGACY_MANAGER_AGENT_UUIDS``; otherwise ``None`` (new pipeline).
    """
    agent = getattr(project, "manager_agent", None)
    if agent is None:
        return None
    if is_legacy_manager_uuid(getattr(agent, "uuid", None)):
        return LEGACY_PIPELINE_VERSION
    return None
