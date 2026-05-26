"""Expose AgentSystem catalog for dedicated GET /api/v1/official/available-systems."""

from nexus.inline_agents.api.serializers import AgentSystemSerializer
from nexus.inline_agents.models import AgentSystem


def available_systems_response_data() -> dict[str, list]:
    """Return the same shape previously nested under official agents list ``new.available_systems``."""
    all_systems = AgentSystem.objects.all()
    systems_data = AgentSystemSerializer(all_systems, many=True).data
    return {"available_systems": systems_data}
