"""Serialize InlineAgentsConfiguration for router Redis cache (pre-generation / composite)."""

from typing import Any, Dict, Optional


def inline_agent_config_dict_for_cache(config) -> Optional[Dict[str, Any]]:
    """Build the dict stored under project:{uuid}:inline_agent_config.

    Must match fields consumers read (e.g. CachedProjectData / invoke kwargs), not a non-existent
    ``configuration`` attribute on the model.
    """
    if not config:
        return None
    return {
        "agents_backend": config.agents_backend,
        "default_instructions_for_collaborators": config.default_instructions_for_collaborators,
        "audio_orchestration": config.audio_orchestration,
        "audio_orchestration_voice": config.audio_orchestration_voice,
    }
