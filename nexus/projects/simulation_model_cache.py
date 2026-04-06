"""Redis keys and TTL for simulation manager model override (scoped per project + contact URN)."""

import hashlib

SIMULATION_MANAGER_MODEL_TTL_SECONDS = 86400
_KEY_PREFIX = "simulation_manager_model"


def simulation_manager_model_redis_key(project_uuid: str, contact_urn: str) -> str:
    """Stable Redis key from project and raw contact URN (hashed for safety)."""
    urn_norm = (contact_urn or "").strip()
    digest = hashlib.sha256(urn_norm.encode("utf-8")).hexdigest()[:24]
    return f"{_KEY_PREFIX}:{project_uuid}:{digest}"
