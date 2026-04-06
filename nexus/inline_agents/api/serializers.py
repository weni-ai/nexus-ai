from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from nexus.inline_agents.api.views import _sort_mcps, _sort_systems, get_all_mcps_for_group, get_all_systems_for_group
from nexus.inline_agents.models import Agent, AgentCredential, AgentSystem, IntegratedAgent
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase


def official_agent_modal_presentation_payload(modal) -> dict:
    """Presentation for official agent APIs (en, es, pt); frontend picks by project language."""
    return {
        "agent_name": modal.agent_name,
        "about_en": modal.about_en,
        "about_es": modal.about_es,
        "about_pt": modal.about_pt,
        "conversation_example_en": modal.conversation_example_en,
        "conversation_example_es": modal.conversation_example_es,
        "conversation_example_pt": modal.conversation_example_pt,
    }


def _official_detail_group_name(agent: Agent, group_context: str | None) -> str | None:
    if group_context:
        return group_context
    group = getattr(agent, "group", None)
    return group.slug if group else None


def _official_detail_available_systems(group_name: str | None, agent: Agent) -> list:
    if group_name:
        return get_all_systems_for_group(group_name)
    systems_list = list(AgentSystem.objects.filter(agents__uuid=agent.uuid).values_list("slug", flat=True).distinct())
    return _sort_systems(systems_list)


def _official_detail_flat_mcps(group_name: str | None) -> list:
    if not group_name:
        return []
    combined = []
    for mcps in get_all_mcps_for_group(group_name).values():
        combined.extend(mcps)
    return combined


def _official_detail_resolve_mcp(system_mcps: list, mcp_name: str | None):
    if not mcp_name or not system_mcps:
        return None, []
    match = next((m for m in system_mcps if m.get("name") == mcp_name), None)
    if match:
        return match, match.get("credentials", [])
    return {}, []


def _official_detail_display_name(agent: Agent, group_name: str | None) -> str:
    name = agent.name
    if getattr(agent, "group", None):
        try:
            modal = agent.group.modal
            if modal and modal.agent_name:
                name = modal.agent_name
        except Exception:
            pass
    if name == agent.name and group_name and "(" in name:
        return name.split("(")[0].strip()
    return name


def _official_detail_attach_mcps_payload(payload: dict, mcp_name: str | None, selected_mcp, system_mcps: list) -> None:
    if mcp_name and selected_mcp:
        payload["MCP"] = selected_mcp
        payload["selected_mcp"] = mcp_name
    else:
        payload["MCPs"] = _sort_mcps(system_mcps)


def _official_detail_attach_presentation(payload: dict, agent: Agent) -> None:
    if not getattr(agent, "group", None):
        return
    try:
        payload["presentation"] = official_agent_modal_presentation_payload(agent.group.modal)
    except ObjectDoesNotExist:
        pass


def inline_agent_list_display_name(agent: Agent) -> str:
    """User-facing label for agent lists: group name (or modal catalog name), not internal template name."""
    if not getattr(agent, "group_id", None):
        raw = agent.name
        return raw.split("(")[0].strip() if "(" in raw else raw
    group = agent.group
    try:
        modal = group.modal
        if modal.agent_name:
            return modal.agent_name
    except ObjectDoesNotExist:
        pass
    return group.name


class AgentSystemSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()

    class Meta:
        model = AgentSystem
        fields = ["slug", "name", "logo"]

    def get_logo(self, obj):
        if not obj.logo:
            return None
        return s3FileDatabase().create_presigned_url(obj.logo.name)


class IntegratedAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegratedAgent
        fields = ["uuid", "id", "name", "skills", "is_official", "description", "mcp", "active"]

    active = serializers.BooleanField(source="is_active", read_only=True)
    uuid = serializers.UUIDField(source="agent.uuid")
    name = serializers.SerializerMethodField("get_name")
    id = serializers.SerializerMethodField("get_id")
    skills = serializers.SerializerMethodField("get_skills")
    description = serializers.SerializerMethodField("get_description")
    is_official = serializers.SerializerMethodField("get_is_official")
    mcp = serializers.SerializerMethodField("get_mcp")

    def get_id(self, obj):
        return obj.agent.slug

    def get_name(self, obj):
        return inline_agent_list_display_name(obj.agent)

    def get_description(self, obj):
        return obj.agent.collaboration_instructions

    def get_skills(self, obj):
        if hasattr(obj.agent, "latest_display_skills"):
            return obj.agent.latest_display_skills
        if obj.agent.current_version:
            return obj.agent.current_version.display_skills
        return []

    def get_is_official(self, obj):
        return obj.agent.is_official

    def get_mcp(self, obj):
        """Return MCP name and config from IntegratedAgent metadata"""
        if not obj.metadata:
            return None

        mcp_name = obj.metadata.get("mcp")
        mcp_config = obj.metadata.get("mcp_config", {})
        system_slug = obj.metadata.get("system")

        if not mcp_name:
            return None

        config_with_labels = {}
        mcp_description = None

        # Try to find MCP with system if available in metadata, or fallback to name lookup
        mcp = None
        if system_slug:
            try:
                system_obj = AgentSystem.objects.get(slug__iexact=system_slug)
                mcp = (
                    obj.agent.mcps.filter(system=system_obj, name=mcp_name, is_active=True)
                    .select_related("system")
                    .prefetch_related("config_options")
                    .first()
                )
            except AgentSystem.DoesNotExist:
                pass

        # Fallback: find MCP by name within agent's MCPs if not found via system
        if not mcp:
            mcp = (
                obj.agent.mcps.filter(name=mcp_name, is_active=True)
                .select_related("system")
                .prefetch_related("config_options")
                .first()
            )

        if mcp:
            mcp_description = (mcp.description_en or mcp.description_pt or mcp.description_es or "").strip() or None
            if mcp_config:
                name_to_label = {opt.name: opt.label for opt in mcp.config_options.all()}
                for name, value in mcp_config.items():
                    label = name_to_label.get(name, name)
                    config_with_labels[label] = value
            else:
                config_with_labels = mcp_config
        else:
            config_with_labels = mcp_config

        result = {"name": mcp_name, "config": config_with_labels}
        if mcp_description:
            result["description"] = mcp_description

        if mcp and mcp.system:
            result["system"] = {
                "name": mcp.system.name,
                "slug": mcp.system.slug,
                "logo": mcp.system.logo.url if mcp.system.logo else None,
            }

        return result


class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = [
            "uuid",
            "name",
            "description",
            "skills",
            "assigned",
            "active",
            # "external_id",
            "slug",
            "model",
            "is_official",
            "project",
            "credentials",
        ]

    name = serializers.SerializerMethodField("get_list_display_name")
    description = serializers.CharField(source="collaboration_instructions")
    model = serializers.CharField(source="foundation_model")
    skills = serializers.SerializerMethodField("get_skills")
    assigned = serializers.SerializerMethodField("get_is_assigned")
    active = serializers.SerializerMethodField("get_active")

    credentials = serializers.SerializerMethodField("get_credentials")

    def get_list_display_name(self, obj):
        return inline_agent_list_display_name(obj)

    def get_skills(self, obj):
        if obj.current_version:
            display_skills = obj.current_version.display_skills
            return display_skills
        return []

    def get_is_assigned(self, obj):
        project_uuid = self.context.get("project_uuid")
        if not project_uuid:
            return False
        qs = IntegratedAgent.objects.filter(project_id=project_uuid, agent=obj)
        if not self.context.get("include_inactive_integrated"):
            qs = qs.filter(is_active=True)
        return qs.exists()

    def get_active(self, obj):
        """Return whether the IntegratedAgent for this agent+project is active, or None if not integrated."""
        project_uuid = self.context.get("project_uuid")
        if not project_uuid:
            return None
        integrated = IntegratedAgent.objects.filter(project_id=project_uuid, agent=obj).first()
        return integrated.is_active if integrated else False

    def get_credentials(self, obj):
        credentials = obj.agentcredential_set.all().distinct("key")
        return [
            {
                "name": credential.key,
                "label": credential.label,
                "placeholder": credential.placeholder,
                "is_confidential": credential.is_confidential,
            }
            for credential in credentials
        ]


class ProjectCredentialsListSerializer(serializers.ModelSerializer):
    agents_using = serializers.SerializerMethodField("get_agents_using")
    name = serializers.CharField(source="key")
    value = serializers.SerializerMethodField("get_value")

    class Meta:
        model = AgentCredential
        fields = ["name", "label", "placeholder", "is_confidential", "value", "agents_using"]

    def get_agents_using(self, obj):
        qs = IntegratedAgent.objects.filter(project=obj.project)
        if not self.context.get("include_inactive_integrated"):
            qs = qs.filter(is_active=True)
        return [
            {
                "uuid": integrated_agent.agent.uuid,
                "name": inline_agent_list_display_name(integrated_agent.agent),
            }
            for integrated_agent in qs
        ]

    def get_value(self, obj):
        if obj.is_confidential:
            return obj.value
        return obj.decrypted_value


class OfficialAgentListSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField()
    type = serializers.CharField()
    group = serializers.CharField(allow_null=True)
    category = serializers.CharField(allow_blank=True)
    systems = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    assigned = serializers.BooleanField()
    slug = serializers.CharField()
    is_official = serializers.BooleanField()
    credentials = serializers.ListField(child=serializers.DictField(), required=False)

    def to_representation(self, obj):
        project_uuid = self.context.get("project_uuid")
        assigned = False
        if project_uuid:
            assigned = IntegratedAgent.objects.filter(project__uuid=project_uuid, agent=obj, is_active=True).exists()
        from nexus.inline_agents.api.views import get_all_mcps_for_group

        systems = list(AgentSystem.objects.filter(agents__uuid=obj.uuid).values_list("slug", flat=True).distinct())
        group_name = obj.group.slug if getattr(obj, "group", None) else None

        agent_mcps = {}
        if group_name:
            agent_mcps = get_all_mcps_for_group(group_name)

        has_multiple_mcps = False

        for system_slug in systems:
            system_mcps = agent_mcps.get(system_slug, [])
            if isinstance(system_mcps, list) and len(system_mcps) > 1:
                has_multiple_mcps = True
                break

        credentials = []

        if not has_multiple_mcps:
            if hasattr(obj, "agentcredential_set"):
                creds = obj.agentcredential_set.all().distinct("key")
                credentials = [
                    {
                        "name": credential.key,
                        "label": credential.label,
                        "placeholder": credential.placeholder,
                        "is_confidential": credential.is_confidential,
                    }
                    for credential in creds
                ]

        payload = {
            "uuid": obj.uuid,
            "name": obj.name,
            "description": obj.collaboration_instructions,
            "type": (obj.agent_type.slug if getattr(obj, "agent_type", None) else ""),
            "group": group_name,
            "category": (obj.category.slug if getattr(obj, "category", None) else ""),
            "systems": systems,
            "assigned": assigned,
            "slug": obj.slug,
            "is_official": obj.is_official,
            "credentials": credentials,
        }

        return payload

    def _get_meta(self, agent: Agent) -> dict:
        mapper = self.context.get("official_mapper", {})
        return mapper.get(agent.slug, {})


class OfficialAgentDetailSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    type = serializers.CharField()
    group = serializers.CharField()
    category = serializers.CharField()
    system = serializers.CharField()
    systems = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    assigned = serializers.BooleanField()
    MCPs = serializers.ListField(child=serializers.DictField(), required=False)
    MCP = serializers.DictField(required=False)
    selected_mcp = serializers.CharField(required=False, allow_null=True)
    credentials = serializers.ListField()

    def to_representation(self, obj):
        project_uuid = self.context.get("project_uuid")
        system = self.context.get("system")
        mcp_name = self.context.get("mcp")
        group_name = _official_detail_group_name(obj, self.context.get("group"))

        available_systems = _official_detail_available_systems(group_name, obj)
        selected_system = system or (available_systems[0] if available_systems else "")
        assigned = (
            IntegratedAgent.objects.filter(project__uuid=project_uuid, agent=obj, is_active=True).exists()
            if project_uuid
            else False
        )
        system_mcps = _official_detail_flat_mcps(group_name)
        selected_mcp, creds = _official_detail_resolve_mcp(system_mcps, mcp_name)

        payload = {
            "name": _official_detail_display_name(obj, group_name),
            "description": obj.collaboration_instructions,
            "type": (obj.agent_type.slug if getattr(obj, "agent_type", None) else ""),
            "group": group_name,
            "category": (obj.category.slug if getattr(obj, "category", None) else ""),
            "system": selected_system,
            "systems": available_systems,
            "assigned": assigned,
            "credentials": creds,
        }

        _official_detail_attach_mcps_payload(payload, mcp_name, selected_mcp, system_mcps)
        _official_detail_attach_presentation(payload, obj)

        return payload


class CredentialItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    placeholder = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    is_confidential = serializers.BooleanField()
    value = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class OfficialAgentsAssignRequestSerializer(serializers.Serializer):
    """Request body for POST /api/v1/official/agents.

    Note: project_uuid and agent_uuid are passed as query parameters, not in the body.
    """

    assigned = serializers.BooleanField(required=False)
    system = serializers.CharField(required=False)
    mcp = serializers.CharField(required=False)
    mcp_config = serializers.DictField(required=False)
    credentials = serializers.ListField(child=CredentialItemSerializer(), required=False)


class OfficialAgentsAssignResponseSerializer(serializers.Serializer):
    assigned = serializers.BooleanField(required=False)
    assigned_created = serializers.BooleanField(required=False)
    assigned_deleted = serializers.BooleanField(required=False)
    created_credentials = serializers.ListField(child=serializers.CharField(), required=False)
