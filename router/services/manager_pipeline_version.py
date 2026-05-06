"""Read pipeline_version from Project.manager_agent for inline-agent cache payloads."""

from __future__ import annotations


def manager_pipeline_version_from_project(project) -> str | None:
    """
    Return ManagerAgent.manager_extra_args['pipeline_version'] when set, else None.

    Missing manager, non-dict extra_args, or empty string all yield None (new pipeline).
    """
    agent = getattr(project, "manager_agent", None)
    if agent is None:
        return None
    extra = getattr(agent, "manager_extra_args", None) or {}
    if not isinstance(extra, dict):
        return None
    raw = extra.get("pipeline_version")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None
