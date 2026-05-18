"""Shared assign + credentials behavior for official agents v1 and project assign."""

from __future__ import annotations

from rest_framework.response import Response

from nexus.inline_agents.api.official_agents_helpers import get_all_mcps_for_group, get_mcps_for_agent_system
from nexus.inline_agents.models import Agent, AgentSystem
from nexus.projects.models import Project
from nexus.usecases.inline_agents.create import CreateAgentUseCase


class OfficialAgentAssignmentMixin:
    """Credential validation/creation aligned with ``POST /api/v1/official/agents``."""

    def _update_agent_metadata(self, integrated_agent, mcp, mcp_config, system) -> None:
        if not (mcp or mcp_config or system):
            return
        if not integrated_agent.metadata:
            integrated_agent.metadata = {}
        if mcp:
            integrated_agent.metadata["mcp"] = mcp
        if mcp_config:
            integrated_agent.metadata["mcp_config"] = mcp_config
        if system:
            integrated_agent.metadata["system"] = system
        integrated_agent.save(update_fields=["metadata"])

    def _handle_credentials(
        self,
        agent: Agent,
        project: Project,
        credentials_data: list,
        system: str | None,
        mcp: str | None = None,
    ) -> dict | Response:
        system_normalized = system.lower() if system else None

        invalid_system = self._validate_system(agent, system_normalized)
        if invalid_system:
            return invalid_system

        if mcp and system_normalized:
            mcp_error = self._validate_mcp(agent, system_normalized, mcp)
            if mcp_error:
                return mcp_error

        expected_templates = self._get_expected_templates(agent, system_normalized, mcp)
        names_error = self._validate_credentials_names(credentials_data, expected_templates, system)
        if names_error:
            return names_error

        fields_error = self._validate_credentials_fields(credentials_data)
        if fields_error:
            return fields_error

        payload = self._format_credentials_payload(credentials_data)
        created = CreateAgentUseCase().create_credentials(agent, project, payload)
        return {"created_credentials": created}

    def _validate_system(self, agent: Agent, system: str | None) -> Response | None:
        available = list(AgentSystem.objects.filter(agents__uuid=agent.uuid).values_list("slug", flat=True).distinct())
        if system:
            system_lower = system.lower()
            available_lower = [s.lower() for s in available]
            if system_lower not in available_lower:
                return Response({"error": "Invalid system"}, status=422)
        return None

    def _get_expected_templates(self, agent: Agent, system: str | None, mcp: str | None = None) -> list:
        if not system or not mcp:
            return []

        group_slug = agent.group.slug if getattr(agent, "group", None) else None
        if group_slug:
            all_group_mcps = get_all_mcps_for_group(group_slug)
            mcps = []
            for sys_key, sys_mcps in all_group_mcps.items():
                if sys_key.lower() == system.lower():
                    mcps = sys_mcps
                    break
        else:
            mcps = get_mcps_for_agent_system(agent.slug, system)

        if not mcps:
            return []

        target_mcp = next((m for m in mcps if m.get("name") == mcp), None)
        if target_mcp:
            return target_mcp.get("credentials", [])
        return []

    def _validate_mcp(self, agent: Agent, system: str, mcp: str) -> Response | None:
        system_lower = system.lower() if system else None
        group_slug = agent.group.slug if getattr(agent, "group", None) else None
        if group_slug:
            all_group_mcps = get_all_mcps_for_group(group_slug)
            mcps = None
            for sys_key in all_group_mcps.keys():
                if sys_key.lower() == system_lower:
                    mcps = all_group_mcps[sys_key]
                    break
            if mcps is None:
                mcps = []
        else:
            mcps = get_mcps_for_agent_system(agent.slug, system_lower)

        if not isinstance(mcps, list):
            return Response({"error": "Invalid MCP configuration"}, status=422)

        available_mcp_names = [m.get("name") for m in mcps if isinstance(m, dict) and m.get("name")]
        if mcp not in available_mcp_names:
            return Response({"error": "Invalid MCP", "available_mcps": available_mcp_names}, status=422)
        return None

    def _validate_credentials_names(
        self, credentials_data: list, expected_templates: list, system: str | None
    ) -> Response | None:
        if not system:
            return None
        if system and not expected_templates:
            return Response({"error": "Credentials template not found for system"}, status=422)
        expected_names = {tpl.get("name") for tpl in expected_templates}
        provided_names = {item.get("name") for item in credentials_data}
        missing = sorted(list(expected_names - provided_names))
        extra = sorted(list(provided_names - expected_names))
        if missing:
            return Response({"error": "Missing credentials", "missing": missing}, status=422)
        if extra:
            return Response({"error": "Unexpected credentials", "extra": extra}, status=422)
        return None

    def _validate_credentials_fields(self, credentials_data: list) -> Response | None:
        for item in credentials_data:
            name = item.get("name")
            label = item.get("label")
            placeholder = item.get("placeholder")
            is_confidential = item.get("is_confidential", True)
            value = item.get("value")

            if not isinstance(name, str) or not name:
                return Response({"error": "Invalid credential name"}, status=422)
            if not isinstance(label, str) or not label:
                return Response({"error": f"Invalid label for {name}"}, status=422)
            if placeholder is not None and not isinstance(placeholder, str):
                return Response({"error": f"Invalid placeholder for {name}"}, status=422)
            if not isinstance(is_confidential, bool):
                return Response({"error": f"Invalid is_confidential for {name}"}, status=422)
            if value is not None and not isinstance(value, str):
                return Response({"error": f"Invalid value type for {name}"}, status=422)
        return None

    def _format_credentials_payload(self, credentials_data: list) -> dict:
        payload = {}
        for cred_item in credentials_data:
            payload.update(
                {
                    cred_item.get("name"): {
                        "label": cred_item.get("label"),
                        "placeholder": cred_item.get("placeholder"),
                        "is_confidential": cred_item.get("is_confidential", True),
                        "value": cred_item.get("value"),
                    }
                }
            )
        return payload

    def _get_project_or_response(self, project_uuid):
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)
