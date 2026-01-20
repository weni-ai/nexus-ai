import logging

import pendulum
from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from inline_agents.backends import BackendsRegistry
from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.events import notify_async
from nexus.inline_agents.api.serializers import (
    AgentSerializer,
    AgentSystemSerializer,
    IntegratedAgentSerializer,
    OfficialAgentDetailSerializer,
    OfficialAgentListSerializer,
    OfficialAgentsAssignRequestSerializer,
    OfficialAgentsAssignResponseSerializer,
    ProjectCredentialsListSerializer,
)
from nexus.inline_agents.backends.openai.models import ManagerAgent
from nexus.inline_agents.models import Agent, AgentSystem
from nexus.projects.api.permissions import CombinedExternalProjectPermission, ProjectPermission
from nexus.projects.exceptions import ProjectDoesNotExist
from nexus.projects.models import Project
from nexus.usecases.agents.exceptions import SkillFileTooLarge
from nexus.usecases.inline_agents.assign import AssignAgentsUsecase
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.usecases.inline_agents.get import GetInlineAgentsUsecase, GetInlineCredentialsUsecase, GetLogGroupUsecase
from nexus.usecases.inline_agents.update import UpdateAgentUseCase
from nexus.usecases.intelligences.get_by_uuid import (
    create_inline_agents_configuration,
    get_project_and_content_base_data,
)
from nexus.usecases.projects import get_project_by_uuid
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from router.entities import message_factory

logger = logging.getLogger(__name__)

SKILL_FILE_SIZE_LIMIT = settings.SKILL_FILE_SIZE_LIMIT


class PushAgents(APIView):
    permission_classes = [IsAuthenticated]

    def _validate_request(self, request):
        """Validate request data and return processed inputs"""

        def validate_file_size(files):
            for file in files:
                if files[file].size > SKILL_FILE_SIZE_LIMIT * (1024**2):
                    raise SkillFileTooLarge(file)

        files = request.FILES
        validate_file_size(files)

        import json

        logger.debug("InlineAgentsView payload", extra={"keys": list(request.data.keys())})

        agents = json.loads(request.data.get("agents"))
        project_uuid = request.data.get("project_uuid")

        return files, agents, project_uuid

    def _check_can_edit_official_agent(self, agents, user_email):
        for key in agents:
            agent_qs = Agent.objects.filter(slug=key, is_official=True)
            existing_official_agent = agent_qs.exists()
            can_edit = False
            for can_edit_email in settings.OFFICIAL_SMART_AGENT_EDITORS:
                if can_edit_email in user_email:
                    can_edit = True
                    break
            if existing_official_agent and not can_edit:
                return key
        return None

    def post(self, request, *args, **kwargs):
        agent_usecase = CreateAgentUseCase()
        update_agent_usecase = UpdateAgentUseCase()

        files, agents, project_uuid = self._validate_request(request)

        agents = agents["agents"]

        logger.debug("Agents payload", extra={"agent_keys": list(agents.keys()) if isinstance(agents, dict) else None})
        logger.debug("Files payload", extra={"file_count": len(files) if hasattr(files, "__len__") else None})
        official_agent_key = self._check_can_edit_official_agent(agents=agents, user_email=request.user.email)
        if official_agent_key is not None:
            return Response(
                {
                    "error": (
                        f"Permission Error: You are not authorized to edit an official "
                        f"AI Agent {official_agent_key}"
                    )
                },
                status=403,
            )

        try:
            project = Project.objects.get(uuid=project_uuid)
            for key in agents:
                agent_qs = Agent.objects.filter(slug=key, project=project)
                existing_agent = agent_qs.exists()
                if existing_agent:
                    logger.info("Updating agent", extra={"key": key})
                    update_agent_usecase.update_agent(agent_qs.first(), agents[key], project, files)
                else:
                    logger.info("Creating agent", extra={"key": key})
                    agent_usecase.create_agent(key, agents[key], project, files)

            # Fire cache invalidation event for team update (agents are part of team) (async observer)
            notify_async(
                event="cache_invalidation:team",
                project_uuid=project_uuid,
            )

        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)

        return Response({})


def _sort_mcps(mcps: list) -> list:
    """Sort MCPs so that 'Default' appears first, then alphabetical order"""
    if not isinstance(mcps, list):
        return mcps

    def sort_key(mcp):
        name = mcp.get("name", "") if isinstance(mcp, dict) else ""
        is_default = name.lower() == "default"
        return (0 if is_default else 1, name.lower())

    return sorted(mcps, key=sort_key)


def _serialize_mcp(mcp) -> dict:
    """Helper to serialize MCP with config and credentials"""
    mcp_data = {
        "name": mcp.name,
        "description": mcp.description,
        "config": [],
        "credentials": [],
    }

    # Add config options
    for config_option in mcp.config_options.all():
        # For SWITCH, NUMBER, TEXT, CHECKBOX - ensure options is always an empty list
        options = config_option.options
        if config_option.type in ["SWITCH", "NUMBER", "TEXT", "CHECKBOX"]:
            if not isinstance(options, list):
                options = []

        config_item = {
            "name": config_option.name,
            "label": config_option.label,
            "type": config_option.type,
            "options": options,
        }
        # Add default_value if it exists
        if config_option.default_value is not None:
            config_item["default_value"] = config_option.default_value
        mcp_data["config"].append(config_item)

    # Add credentials templates
    for template in mcp.credential_templates.all():
        mcp_data["credentials"].append(
            {
                "name": template.name,
                "label": template.label,
                "placeholder": template.placeholder,
                "is_confidential": template.is_confidential,
            }
        )

    return mcp_data


def get_mcps_for_agent_system(agent_slug: str, system_slug: str) -> list:
    """
    Get MCPs for an agent/system combination from database models.
    """
    from nexus.inline_agents.models import Agent, AgentSystem

    agent = Agent.objects.filter(slug=agent_slug, is_official=True).first()
    system = AgentSystem.objects.filter(slug__iexact=system_slug).first()

    if not agent or not system:
        return []

    mcps = (
        agent.mcps.filter(system=system, is_active=True)
        .select_related("system")
        .prefetch_related("config_options", "credential_templates")
    )

    result = [_serialize_mcp(mcp) for mcp in mcps]
    return _sort_mcps(result)


def get_all_mcps_for_agent(agent_slug: str) -> dict:
    """
    Get all MCPs for an agent organized by system, from database models.
    """
    from nexus.inline_agents.models import Agent

    agent = Agent.objects.filter(slug=agent_slug, is_official=True).first()
    if not agent:
        return {}

    mcps = (
        agent.mcps.filter(is_active=True)
        .select_related("system")
        .prefetch_related("config_options", "credential_templates")
    )

    result = {}
    for mcp in mcps:
        system_slug = mcp.system.slug
        if system_slug not in result:
            result[system_slug] = []

        result[system_slug].append(_serialize_mcp(mcp))

    # Sort MCPs for each system
    for system_slug in result:
        result[system_slug] = _sort_mcps(result[system_slug])

    return result


def get_all_mcps_for_group(group_slug: str) -> dict:
    """
    Get all MCPs for all agents in a group, organized by system.
    Consolidates MCPs from all agents in the group.
    """
    from nexus.inline_agents.models import AgentGroup

    group = AgentGroup.objects.filter(slug=group_slug).first()
    if not group:
        return {}

    agents = Agent.objects.filter(group=group, is_official=True, source_type=Agent.PLATFORM)
    result = {}

    for agent in agents:
        agent_mcps = get_all_mcps_for_agent(agent.slug)
        for system_slug, mcps in agent_mcps.items():
            if system_slug not in result:
                result[system_slug] = []
            # Add MCPs, avoiding duplicates by name
            existing_mcp_names = {mcp["name"] for mcp in result[system_slug]}
            for mcp in mcps:
                if mcp["name"] not in existing_mcp_names:
                    result[system_slug].append(mcp)
                    existing_mcp_names.add(mcp["name"])

    # Sort MCPs for each system
    for system_slug in result:
        result[system_slug] = _sort_mcps(result[system_slug])

    return result


def get_all_credentials_for_group(group_slug: str) -> list:
    """
    Get all credentials for all agents in a group.
    Consolidates credentials from all agents in the group.
    """
    from nexus.inline_agents.models import AgentGroup

    group = AgentGroup.objects.filter(slug=group_slug).first()
    if not group:
        return []

    agents = Agent.objects.filter(group=group, is_official=True, source_type=Agent.PLATFORM)
    all_credentials = []
    seen_credential_keys = set()

    for agent in agents:
        if hasattr(agent, "agentcredential_set"):
            creds = agent.agentcredential_set.all().distinct("key")
            for credential in creds:
                if credential.key not in seen_credential_keys:
                    all_credentials.append(
                        {
                            "name": credential.key,
                            "label": credential.label,
                            "placeholder": credential.placeholder,
                            "is_confidential": credential.is_confidential,
                        }
                    )
                    seen_credential_keys.add(credential.key)

    return all_credentials


def consolidate_grouped_agents(agents_queryset, project_uuid: str = None) -> dict:
    """
    Consolidate agents that belong to the same group into a single entry with variants list.
    Returns a dict with 'legacy' and 'new' keys separating legacy agents from grouped agents.
    For grouped agents, returns consolidated group data with a list of available variants.
    """
    from collections import defaultdict

    from nexus.inline_agents.api.serializers import OfficialAgentListSerializer
    from nexus.inline_agents.models import IntegratedAgent

    agents_by_group = defaultdict(list)
    for agent in agents_queryset:
        if "concierge" in agent.slug.lower() and agent.group is None:
            continue

        if agent.group:
            agents_by_group[agent.group.slug].append(agent)
        else:
            agents_by_group[None].append(agent)

    legacy_agents = []
    new_agents = []

    for group_slug, group_agents in agents_by_group.items():
        if group_slug is None:
            for agent in group_agents:
                serializer = OfficialAgentListSerializer(agent, context={"project_uuid": project_uuid})
                legacy_agents.append(serializer.data)
        else:
            if not group_agents:
                continue

            base_agent = None
            for agent in group_agents:
                variant = getattr(agent, "variant", None)
                if not variant:
                    base_agent = agent
                    break
            if not base_agent:
                base_agent = group_agents[0]

            group_assigned = False
            if project_uuid:
                agent_uuids = [agent.uuid for agent in group_agents]
                group_assigned = IntegratedAgent.objects.filter(
                    project__uuid=project_uuid, agent__uuid__in=agent_uuids
                ).exists()

            # Get all systems for all agents in this group by querying the intermediate table directly
            # This avoids any influence from the filtered queryset
            all_group_agent_uuids = list(
                Agent.objects.filter(group__slug=group_slug, is_official=True, source_type=Agent.PLATFORM).values_list(
                    "uuid", flat=True
                )
            )
            # Query AgentSystem directly through the intermediate table, bypassing any queryset cache
            all_systems = set(
                AgentSystem.objects.filter(agents__uuid__in=all_group_agent_uuids)
                .values_list("slug", flat=True)
                .distinct()
            )

            group_mcps = get_all_mcps_for_group(group_slug)
            has_multiple_mcps = False
            for system_slug in all_systems:
                system_mcps = group_mcps.get(system_slug, [])
                if isinstance(system_mcps, list) and len(system_mcps) > 1:
                    has_multiple_mcps = True
                    break

            credentials = []
            if not has_multiple_mcps:
                credentials = get_all_credentials_for_group(group_slug)

            # Consolidate capabilities, policies, tooling, catalog from all agents
            all_capabilities = set()
            all_policies = {}
            all_tooling = {}
            all_catalog = {}

            for agent in group_agents:
                if isinstance(getattr(agent, "capabilities", []), list):
                    all_capabilities.update(agent.capabilities)
                if isinstance(getattr(agent, "policies", {}), dict):
                    all_policies.update(agent.policies)
                if isinstance(getattr(agent, "tooling", {}), dict):
                    all_tooling.update(agent.tooling)
                if isinstance(getattr(agent, "catalog", {}), dict):
                    all_catalog.update(agent.catalog)

            variants = []
            for agent in group_agents:
                variant_assigned = False
                if project_uuid:
                    variant_assigned = IntegratedAgent.objects.filter(project__uuid=project_uuid, agent=agent).exists()

                # Query systems directly through the intermediate table for this specific agent
                # This ensures we get all systems regardless of any filters applied to the queryset
                variant_systems = list(
                    AgentSystem.objects.filter(agents__uuid=agent.uuid).values_list("slug", flat=True).distinct()
                )

                variant_data = {
                    "uuid": agent.uuid,
                    "name": agent.name,
                    "slug": agent.slug,
                    "variant": getattr(agent, "variant", None),
                    "systems": variant_systems,
                    "assigned": variant_assigned,
                }
                variants.append(variant_data)

            def sort_key(v):
                variant = v["variant"]
                is_default = variant is None or (isinstance(variant, str) and variant.lower() == "default")
                return (0 if is_default else 1, variant or "")

            variants.sort(key=sort_key)

            generic_name = base_agent.name
            if "(" in generic_name:
                generic_name = generic_name.split("(")[0].strip()

            payload = {
                "group": group_slug,
                "name": generic_name,
                "slug": base_agent.slug,
                "description": base_agent.collaboration_instructions,
                "type": (base_agent.agent_type.slug if getattr(base_agent, "agent_type", None) else ""),
                "category": (base_agent.category.slug if getattr(base_agent, "category", None) else ""),
                "systems": sorted(list(all_systems), key=lambda s: (0 if "vtex" in s.lower() else 1, s.lower())),
                "assigned": group_assigned,
                "is_official": base_agent.is_official,
                "credentials": credentials,
                "variants": variants,  # List of available variants
            }

            try:
                modal = base_agent.group.modal
                presentation = {"conversation_example": modal.conversation_example}
                payload["presentation"] = presentation
            except Exception:
                pass

            if len(all_capabilities) > 0:
                payload["capabilities"] = sorted(list(all_capabilities))
            if len(all_policies) > 0:
                payload["policies"] = all_policies
            if len(all_tooling) > 0:
                payload["tooling"] = all_tooling
            if len(all_catalog) > 0:
                payload["catalog"] = all_catalog

            new_agents.append(payload)

    return {"legacy": legacy_agents, "new": new_agents}


class OfficialAgentsV1(APIView):
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [CombinedExternalProjectPermission]

    @extend_schema(
        operation_id="v1_official_agents_list",
        summary="List official agents",
        description=(
            "Returns available official agents separated into 'legacy' and 'new' keys. "
            "Legacy agents (without group) are returned individually. "
            "New agents (with group) are consolidated by group with consolidated systems, MCPs, and credentials. "
            "Each grouped agent includes a 'variants' array listing all available variants with their UUIDs, "
            "allowing the frontend to select which variant to view details for. "
            "Optional filters: `type`, `group`, `category`, `system`. Use `project_uuid` to mark `assigned`."
        ),
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.QUERY,
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(name="name", location=OpenApiParameter.QUERY, required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="type", location=OpenApiParameter.QUERY, required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="group", location=OpenApiParameter.QUERY, required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="category", location=OpenApiParameter.QUERY, required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="system", location=OpenApiParameter.QUERY, required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="variant", location=OpenApiParameter.QUERY, required=False, type=OpenApiTypes.STR),
        ],
        responses={
            200: OpenApiResponse(description="Agents list", response=OfficialAgentListSerializer),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
        },
        tags=["Agents"],
    )
    def get(self, request, *args, **kwargs):
        project_uuid = request.query_params.get("project_uuid")
        name_filter = request.query_params.get("name")
        type_filter = request.query_params.get("type")
        group_filter = request.query_params.get("group")
        category_filter = request.query_params.get("category")
        system_filter = request.query_params.get("system")
        variant_filter = request.query_params.get("variant")

        agents = Agent.objects.filter(is_official=True, source_type=Agent.PLATFORM)
        agents = agents.exclude(Q(slug__icontains="concierge") & Q(group__isnull=True))
        if name_filter:
            agents = agents.filter(name__icontains=name_filter)
        if type_filter:
            agents = agents.filter(agent_type__slug__iexact=type_filter)
        if group_filter:
            agents = agents.filter(group__slug__iexact=group_filter)
        if category_filter:
            if category_filter.lower() == "others":
                agents = agents.filter(category__isnull=True)
            else:
                agents = agents.filter(category__slug__iexact=category_filter)
        if system_filter:
            # Extract UUIDs from filtered queryset, then fetch agents again without the systems filter
            # This prevents the filtered queryset from affecting subsequent system queries
            agent_uuids = list(
                agents.filter(systems__slug__iexact=system_filter).distinct("uuid").values_list("uuid", flat=True)
            )
            # Fetch agents again without the systems filter to avoid queryset state issues
            agents = Agent.objects.filter(uuid__in=agent_uuids, is_official=True, source_type=Agent.PLATFORM)
            agents = agents.exclude(Q(slug__icontains="concierge") & Q(group__isnull=True))
        if variant_filter:
            agents = agents.filter(variant__iexact=variant_filter)

        consolidated_data = consolidate_grouped_agents(agents, project_uuid=project_uuid)

        all_systems = AgentSystem.objects.all()
        systems_data = AgentSystemSerializer(all_systems, many=True).data

        response_data = {
            "legacy": consolidated_data.get("legacy", []),
            "new": {"agents": consolidated_data.get("new", []), "available_systems": systems_data},
        }

        return Response(response_data)

    @extend_schema(
        operation_id="v1_official_agents_assign",
        summary="Assign official agent to project and/or configure credentials",
        description=(
            "Assigns or removes an official agent (`assigned`) and optionally creates credentials. "
            "When `system` is provided, `credentials` must follow the system template. "
            "When `mcp` is provided, `credentials` must follow the MCP-specific template for that system. "
            "`project_uuid` and `agent_uuid` are required query parameters. "
            "All other fields (`assigned`, `credentials`, `system`, `mcp`, `mcp_config`) are sent in the request body."
        ),
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.QUERY,
                required=True,
                type=OpenApiTypes.UUID,
                description="Project UUID to assign the agent to",
            ),
            OpenApiParameter(
                name="agent_uuid",
                location=OpenApiParameter.QUERY,
                required=True,
                type=OpenApiTypes.UUID,
                description="Official agent UUID to assign",
            ),
        ],
        request=OfficialAgentsAssignRequestSerializer,
        responses={
            200: OpenApiResponse(description="Operation performed", response=OfficialAgentsAssignResponseSerializer),
            400: OpenApiResponse(description="Bad request"),
            404: OpenApiResponse(description="Not found"),
            422: OpenApiResponse(description="Unprocessable Entity"),
        },
        tags=["Agents"],
    )
    def post(self, request, *args, **kwargs):
        project_uuid = request.query_params.get("project_uuid")
        agent_uuid = request.query_params.get("agent_uuid")
        assigned = request.data.get("assigned")
        credentials_data = request.data.get("credentials", [])
        system = request.data.get("system")
        mcp = request.data.get("mcp")
        mcp_config = request.data.get("mcp_config", {})

        if not project_uuid or not agent_uuid:
            return Response({"error": "project_uuid and agent_uuid are required"}, status=400)

        try:
            project = Project.objects.get(uuid=project_uuid)
            agent = Agent.objects.get(uuid=agent_uuid, is_official=True, source_type=Agent.PLATFORM)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        result = {}

        from nexus.inline_agents.api.serializers import OfficialAgentListSerializer

        agent_serializer = OfficialAgentListSerializer(agent, context={"project_uuid": project_uuid})
        result["agent"] = agent_serializer.data

        if assigned is not None:
            assignment_result = self._handle_assignment(agent_uuid, project_uuid, assigned, mcp, mcp_config, system)
            if isinstance(assignment_result, Response):
                return assignment_result
            result.update(assignment_result)

        if credentials_data:
            creds_result = self._handle_credentials(agent, project, credentials_data, system, mcp)
            if isinstance(creds_result, Response):
                return creds_result
            result.update(creds_result)

        return Response(result or {"message": "No changes applied", "agent": agent_serializer.data}, status=200)

    def _handle_assignment(
        self,
        agent_uuid: str,
        project_uuid: str,
        assigned: bool,
        mcp: str | None = None,
        mcp_config: dict | None = None,
        system: str | None = None,
    ) -> dict | Response:
        usecase = AssignAgentsUsecase()
        if assigned:
            try:
                created, integrated_agent = usecase.assign_agent(agent_uuid, project_uuid)

                # Persist MCP selection and configuration in metadata
                if mcp or mcp_config or system:
                    if not integrated_agent.metadata:
                        integrated_agent.metadata = {}
                    if mcp:
                        integrated_agent.metadata["mcp"] = mcp
                    if mcp_config:
                        integrated_agent.metadata["mcp_config"] = mcp_config
                    if system:
                        integrated_agent.metadata["system"] = system
                    integrated_agent.save(update_fields=["metadata"])

                return {"assigned": True, "assigned_created": created}
            except ValueError as e:
                return Response({"error": str(e)}, status=404)
        try:
            usecase.unassign_agent(agent_uuid, project_uuid)
            return {"assigned": False}
        except ValueError as e:
            return Response({"error": str(e)}, status=404)

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

        # Validate MCP if provided
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

        # If agent has a group, search across all agents in the group
        group_slug = agent.group.slug if getattr(agent, "group", None) else None

        # Use existing helper to find MCPs
        if group_slug:
            all_group_mcps = get_all_mcps_for_group(group_slug)
            mcps = []
            for sys_key, sys_mcps in all_group_mcps.items():
                if sys_key.lower() == system.lower():
                    mcps = sys_mcps
                    break
        else:
            mcps = get_mcps_for_agent_system(agent.slug, system)

        # Find the specific MCP and return its credentials
        if not mcps:
            return []

        target_mcp = next((m for m in mcps if m.get("name") == mcp), None)
        if target_mcp:
            return target_mcp.get("credentials", [])

        return []

    def _validate_mcp(self, agent: Agent, system: str, mcp: str) -> Response | None:
        """Validate that the MCP exists for the given agent and system."""
        system_lower = system.lower() if system else None

        # If agent has a group, get MCPs from all agents in the group
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


class OfficialAgentDetailV1(APIView):
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [CombinedExternalProjectPermission]

    @extend_schema(
        operation_id="v1_official_agent_detail",
        summary="Get official agent details",
        description=(
            "Returns details of the official agent, MCPs and expected credentials for the selected `system`. "
            "MCPs are loaded from the database (configured via Django admin). "
            "Provide `project_uuid` to check if it is `assigned`. "
            "Provide `mcp` to get details for a specific MCP (returns single MCP object with credentials), "
            "otherwise returns all available MCPs for the system (returns MCPs list without credentials)."
        ),
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.QUERY,
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(name="system", location=OpenApiParameter.QUERY, required=False, type=OpenApiTypes.STR),
            OpenApiParameter(
                name="mcp",
                location=OpenApiParameter.QUERY,
                required=False,
                type=OpenApiTypes.STR,
                description="Specific MCP name to retrieve. If not provided, returns all available MCPs.",
            ),
            OpenApiParameter(name="agent_uuid", location=OpenApiParameter.PATH, required=True, type=OpenApiTypes.STR),
        ],
        responses={
            200: OpenApiResponse(description="Agent detail", response=OfficialAgentDetailSerializer),
            404: OpenApiResponse(description="Agent not found"),
        },
        tags=["Agents"],
    )
    def get(self, request, *args, **kwargs):
        agent_uuid = kwargs.get("agent_uuid")
        project_uuid = request.query_params.get("project_uuid")
        system = request.query_params.get("system")
        mcp = request.query_params.get("mcp")

        try:
            agent = Agent.objects.get(uuid=agent_uuid, is_official=True, source_type=Agent.PLATFORM)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        serializer = OfficialAgentDetailSerializer(
            agent,
            context={
                "project_uuid": project_uuid,
                "system": system,
                "mcp": mcp,
            },
        )
        return Response(serializer.data)


class ActiveAgentsView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        agent_uuid = kwargs.get("agent_uuid")
        assign: bool = request.data.get("assigned")

        usecase = AssignAgentsUsecase()

        try:
            if assign:
                usecase.assign_agent(agent_uuid, project_uuid)

                # Fire cache invalidation event for team update (agent assigned) (async observer)
                notify_async(
                    event="cache_invalidation:team",
                    project_uuid=project_uuid,
                )

                return Response({"assigned": True}, status=200)

            usecase.unassign_agent(agent_uuid, project_uuid)

            # Fire cache invalidation event for team update (agent unassigned) (async observer)
            notify_async(
                event="cache_invalidation:team",
                project_uuid=project_uuid,
            )

            return Response({"assigned": False}, status=200)
        except ValueError as e:
            return Response({"error": str(e)}, status=404)


class AgentsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(project__uuid=project_uuid)

        if search:
            query_filter = Q(name__icontains=search)
            agents = agents.filter(query_filter).distinct("uuid")

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class TeamView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        usecase = GetInlineAgentsUsecase()
        agents = usecase.get_active_agents(project_uuid)
        serializer = IntegratedAgentSerializer(agents, many=True)

        data = {"manager": {"external_id": ""}, "agents": serializer.data}
        return Response(data)


class OfficialAgentsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        # TODO: filter skills
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(is_official=True, source_type=Agent.PLATFORM)

        if search:
            query_filter = Q(name__icontains=search)
            agents = agents.filter(query_filter).distinct("uuid")

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class ProjectCredentialsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        usecase = GetInlineCredentialsUsecase()
        official_credentials, custom_credentials = usecase.get_credentials_by_project(project_uuid)
        return Response(
            {
                "official_agents_credentials": ProjectCredentialsListSerializer(official_credentials, many=True).data,
                "my_agents_credentials": ProjectCredentialsListSerializer(custom_credentials, many=True).data,
            }
        )

    def patch(self, request, project_uuid):
        credentials_data = request.data

        updated_credentials = []
        for key, value in credentials_data.items():
            usecase = UpdateAgentUseCase()
            updated = usecase.update_credential_value(project_uuid, key, value)
            if updated:
                updated_credentials.append(key)

        return Response({"message": "Credentials updated successfully", "updated_credentials": updated_credentials})

    def post(self, request, project_uuid):
        credentials_data = request.data.get("credentials", [])
        agent_uuid = request.data.get("agent_uuid")

        if not agent_uuid or not credentials_data:
            return Response({"error": "agent_uuid and credentials are required"}, status=400)

        try:
            agent = Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        credentials = {}
        for cred_item in credentials_data:
            credentials.update(
                {
                    cred_item.get("name"): {
                        "label": cred_item.get("label"),
                        "placeholder": cred_item.get("placeholder"),
                        "is_confidential": cred_item.get("is_confidential", True),
                        "value": cred_item.get("value"),
                    },
                }
            )

        created_credentials = CreateAgentUseCase().create_credentials(
            agent, Project.objects.get(uuid=project_uuid), credentials
        )

        return Response({"message": "Credentials created successfully", "created_credentials": created_credentials})


class InternalCommunicationPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.has_perm("users.can_communicate_internally")


class VtexAppActiveAgentsView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def patch(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        agent_uuid = kwargs.get("agent_uuid")
        assign: bool = request.data.get("assigned")

        usecase = AssignAgentsUsecase()

        try:
            if assign:
                usecase.assign_agent(agent_uuid, project_uuid)

                # Fire cache invalidation event for team update (agent assigned)
                notify_async(
                    event="cache_invalidation:team",
                    project_uuid=project_uuid,
                )

                return Response({"assigned": True}, status=200)

            usecase.unassign_agent(agent_uuid, project_uuid)

            # Fire cache invalidation event for team update (agent unassigned)
            notify_async(
                event="cache_invalidation:team",
                project_uuid=project_uuid,
            )

            return Response({"assigned": False}, status=200)
        except ValueError as e:
            return Response({"error": str(e)}, status=404)


class VtexAppAgentsView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(project__uuid=project_uuid)

        if search:
            query_filter = Q(name__icontains=search)
            agents = agents.filter(query_filter).distinct("uuid")

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class VtexAppOfficialAgentsView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, *args, **kwargs):
        # TODO: filter skills
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(is_official=True, source_type=Agent.VTEX_APP)

        if search:
            query_filter = Q(name__icontains=search)
            agents = agents.filter(query_filter).distinct("uuid")

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class VTexAppTeamView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        usecase = GetInlineAgentsUsecase()
        agents = usecase.get_active_agents(project_uuid)
        serializer = IntegratedAgentSerializer(agents, many=True)

        data = {"manager": {"external_id": ""}, "agents": serializer.data}
        return Response(data)


class VtexAppProjectCredentialsView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, project_uuid):
        usecase = GetInlineCredentialsUsecase()
        official_credentials, custom_credentials = usecase.get_credentials_by_project(project_uuid)
        return Response(
            {
                "official_agents_credentials": ProjectCredentialsListSerializer(official_credentials, many=True).data,
                "my_agents_credentials": ProjectCredentialsListSerializer(custom_credentials, many=True).data,
            }
        )

    def patch(self, request, project_uuid):
        credentials_data = request.data

        updated_credentials = []
        for key, value in credentials_data.items():
            usecase = UpdateAgentUseCase()
            updated = usecase.update_credential_value(project_uuid, key, value)
            if updated:
                updated_credentials.append(key)

        return Response({"message": "Credentials updated successfully", "updated_credentials": updated_credentials})

    def post(self, request, project_uuid):
        credentials_data = request.data.get("credentials", [])
        agent_uuid = request.data.get("agent_uuid")

        if not agent_uuid or not credentials_data:
            return Response({"error": "agent_uuid and credentials are required"}, status=400)

        try:
            agent = Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        credentials = {}
        for cred_item in credentials_data:
            credentials.update(
                {
                    cred_item.get("name"): {
                        "label": cred_item.get("label"),
                        "placeholder": cred_item.get("placeholder"),
                        "is_confidential": cred_item.get("is_confidential", True),
                        "value": cred_item.get("value"),
                    },
                }
            )

        created_credentials = CreateAgentUseCase().create_credentials(
            agent, Project.objects.get(uuid=project_uuid), credentials
        )

        return Response({"message": "Credentials created successfully", "created_credentials": created_credentials})


class ProjectComponentsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        try:
            project = Project.objects.get(uuid=project_uuid)
            return Response({"use_components": project.use_components})
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)

    def patch(self, request, project_uuid):
        use_components = request.data.get("use_components")

        if use_components is None:
            return Response({"error": "use_components field is required"}, status=400)

        try:
            project = Project.objects.get(uuid=project_uuid)
            project.use_components = use_components
            project.save()

            # Fire cache invalidation event for project update
            notify_async(
                event="cache_invalidation:project",
                project=project,
            )

            return Response({"message": "Project updated successfully", "use_components": use_components})
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)


class LogGroupView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = request.query_params.get("project")
        agent_key = request.query_params.get("agent_key")
        tool_key = request.query_params.get("tool_key")

        if not project_uuid or not agent_key or not tool_key:
            return Response({"error": "project, agent_key and tool_key are required"}, status=400)
        try:
            usecase = GetLogGroupUsecase()
            log_group = usecase.get_log_group(project_uuid, agent_key, tool_key)
        except Agent.DoesNotExist:
            return Response({"error": f"Agent {agent_key} not found in project {project_uuid}"}, status=404)

        return Response({"log_group": log_group})


class MultiAgentView(APIView):
    permission_classes = [CombinedExternalProjectPermission]
    authentication_classes = []  # Disable default authentication

    def get(self, request, project_uuid):
        if not project_uuid:
            return Response({"error": "project is required"}, status=400)

        try:
            project = Project.objects.get(uuid=project_uuid)

            return Response(
                {
                    "multi_agents": project.inline_agent_switch,
                }
            )
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    def patch(self, request, project_uuid):
        multi_agents = request.data.get("multi_agents")
        if multi_agents is None:
            return Response({"error": "multi_agents field is required"}, status=400)

        try:
            project = Project.objects.get(uuid=project_uuid)

            # AB 1.0 projects have inline_agent_switch=False and use BedrockBackend
            is_legacy_project_enabling = (
                not project.inline_agent_switch and multi_agents and project.agents_backend == "BedrockBackend"
            )
            project.inline_agent_switch = multi_agents
            # Migrate legacy projects (AB 1.0) to AB 2.5 (OpenAI)
            if is_legacy_project_enabling:
                project.agents_backend = "OpenAIBackend"

            if not project.use_prompt_creation_configurations:
                project.use_prompt_creation_configurations = True
            project.save()

            # Fire cache invalidation event for project update (async observer)
            notify_async(
                event="cache_invalidation:project",
                project=project,
            )

            return Response({"message": "Project updated successfully", "multi_agents": multi_agents}, status=200)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


class AgentEndSessionView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def post(self, request, project_uuid):
        contact_urn = request.data.get("contact_urn")
        if not contact_urn:
            return Response({"error": "contact_urn is required"}, status=400)

        message_obj = message_factory(text="", project_uuid=project_uuid, contact_urn=contact_urn)

        projects_use_case = ProjectsUseCase()
        agents_backend = projects_use_case.get_agents_backend_by_project(project_uuid)
        backend = BackendsRegistry.get_backend(agents_backend) if BackendsRegistry else None
        backend.end_session(message_obj.project_uuid, message_obj.sanitized_urn)
        return Response({"message": "Agent session ended successfully"})


class AgentBuilderAudio(APIView):
    def get(self, request, project_uuid):
        _, _, inline_agents_configuration = get_project_and_content_base_data(project_uuid=project_uuid)
        if inline_agents_configuration:
            return Response(
                {
                    "audio_orchestration": inline_agents_configuration.audio_orchestration,
                    "agent_voice": inline_agents_configuration.audio_orchestration_voice,
                }
            )

        return Response({"audio_orchestration": False, "agent_voice": None})

    def post(self, request, project_uuid):
        agent_voice = request.data.get("agent_voice")
        audio_orchestration = request.data.get("audio_orchestration")

        if not agent_voice and audio_orchestration is None:
            return Response({"error": "At least one of 'audio_orchestration' or 'agent_voice' is required"}, status=400)

        try:
            project, _, inline_agents_configuration = get_project_and_content_base_data(project_uuid=project_uuid)

            if inline_agents_configuration is None:
                inline_agents_configuration = create_inline_agents_configuration(
                    project, audio_orchestration=audio_orchestration, audio_orchestration_voice=agent_voice
                )

            if audio_orchestration is not None and agent_voice:
                inline_agents_configuration.set_audio_orchestration(audio_orchestration, agent_voice)

            elif audio_orchestration is not None:
                inline_agents_configuration.set_audio_orchestration(audio_orchestration)

            elif agent_voice:
                inline_agents_configuration.set_audio_orchestration_voice(agent_voice)

            # Fire cache invalidation event for project update (async observer)
            notify_async(
                event="cache_invalidation:project",
                project=project,
            )

            return Response(
                {
                    "audio_orchestration": inline_agents_configuration.audio_orchestration,
                    "agent_voice": inline_agents_configuration.audio_orchestration_voice,
                },
                status=200,
            )

        except ValueError:
            return Response({"error": "Invalid voice option"}, status=400)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


def set_project_manager_agent(project_uuid, manager_uuid: str):
    project = get_project_by_uuid(project_uuid)

    manager = ManagerAgent.objects.get(uuid=manager_uuid)
    project.manager_agent = manager
    project.save()

    notify_async(
        event="cache_invalidation:project",
        project=project,
    )

    return project.manager_agent.uuid


def get_default_managers(limit: int = 2):
    return ManagerAgent.objects.filter(default=True, public=True).order_by("-created_on")[:limit]


class AgentManagersView(APIView):
    # changing the supervisor agent naming to manager agent
    def post(self, request, project_uuid):
        manager_uuid = request.data.get("currentManager")
        try:
            manager_agent_uuid = set_project_manager_agent(project_uuid, manager_uuid)
        except ManagerAgent.DoesNotExist:
            return Response(data={"error": "Manager agent not found"}, status=404)
        except ProjectDoesNotExist:
            return Response(data={"error": "Project not found"}, status=404)

        return Response(data={"currentManager": manager_agent_uuid})

    def get(self, request, project_uuid):
        try:
            project = get_project_by_uuid(project_uuid)
        except ProjectDoesNotExist:
            return Response(data={"error": "Project not found"}, status=404)

        data = {
            "serverTime": str(pendulum.now()),
        }
        current_manager: ManagerAgent | None = project.manager_agent

        if not current_manager:
            return Response(data=data)

        data.update({"currentManager": str(current_manager.uuid)})

        if current_manager.default:
            managers = get_default_managers(limit=2)
            if managers.count() == 2:
                new_manager = managers[0]
                legacy_manager = managers[1]
                manager_data = {
                    "new": {"id": str(new_manager.uuid), "label": new_manager.name},
                    "legacy": {
                        "id": str(legacy_manager.uuid),
                        "label": legacy_manager.name,
                        "deprecation": str(pendulum.instance(new_manager.release_date).subtract(days=1)),
                    },
                }
            else:
                manager_data = {
                    "new": {"id": str(new_manager.uuid), "label": new_manager.name},
                }
            data.update(manager_data)
            return Response(data=data)

        return Response(data=data)
