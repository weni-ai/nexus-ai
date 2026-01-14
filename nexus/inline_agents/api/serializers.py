from rest_framework import serializers

from nexus.inline_agents.models import MCP, Agent, AgentCredential, IntegratedAgent


class IntegratedAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegratedAgent
        fields = ["uuid", "id", "name", "skills", "is_official", "description", "mcp"]

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
        return obj.agent.name

    def get_description(self, obj):
        return obj.agent.collaboration_instructions

    def get_skills(self, obj):
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

        if not mcp_name:
            return None

        config_with_labels = {}
        system_info = None

        mcp = (
            MCP.objects.filter(agent=obj.agent, name=mcp_name, is_active=True)
            .select_related("system")
            .prefetch_related("config_options")
            .first()
        )

        if mcp:
            if mcp_config:
                name_to_label = {opt.name: opt.label for opt in mcp.config_options.all()}
                for name, value in mcp_config.items():
                    label = name_to_label.get(name, name)
                    config_with_labels[label] = value
            else:
                config_with_labels = mcp_config

            if mcp.system:
                system_info = {"name": mcp.system.name, "slug": mcp.system.slug}
        else:
            config_with_labels = mcp_config

        result = {"name": mcp_name, "config": config_with_labels}
        if system_info:
            result["system"] = system_info

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
            # "external_id",
            "slug",
            "model",
            "is_official",
            "project",
            "credentials",
        ]

    description = serializers.CharField(source="collaboration_instructions")
    model = serializers.CharField(source="foundation_model")
    skills = serializers.SerializerMethodField("get_skills")
    assigned = serializers.SerializerMethodField("get_is_assigned")

    credentials = serializers.SerializerMethodField("get_credentials")

    def get_skills(self, obj):
        if obj.current_version:
            display_skills = obj.current_version.display_skills
            return display_skills
        return []

    def get_is_assigned(self, obj):
        project_uuid = self.context.get("project_uuid")
        active_agent = IntegratedAgent.objects.filter(project_id=project_uuid, agent=obj)
        return active_agent.exists()

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
        return [
            {
                "uuid": integrated_agent.agent.uuid,
                "name": integrated_agent.agent.name,
            }
            for integrated_agent in IntegratedAgent.objects.filter(project=obj.project)
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
    variant = serializers.CharField(required=False, allow_null=True)
    capabilities = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)
    policies = serializers.DictField(required=False)
    tooling = serializers.DictField(required=False)
    catalog = serializers.DictField(required=False)
    slug = serializers.CharField()
    is_official = serializers.BooleanField()
    credentials = serializers.ListField(child=serializers.DictField(), required=False)

    def to_representation(self, obj):
        project_uuid = self.context.get("project_uuid")
        assigned = False
        if project_uuid:
            assigned = IntegratedAgent.objects.filter(project__uuid=project_uuid, agent=obj).exists()
        from nexus.inline_agents.models import AgentSystem

        systems = list(AgentSystem.objects.filter(agents__uuid=obj.uuid).values_list("slug", flat=True).distinct())
        group_name = obj.group.slug if getattr(obj, "group", None) else None

        from nexus.inline_agents.api.views import get_all_mcps_for_agent

        agent_mcps = get_all_mcps_for_agent(obj.slug)
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

        # Include operational metadata only when configured on the model
        variant = getattr(obj, "variant", None)
        capabilities = getattr(obj, "capabilities", [])
        policies = getattr(obj, "policies", {})
        tooling = getattr(obj, "tooling", {})
        catalog = getattr(obj, "catalog", {})

        if variant is not None:
            payload["variant"] = variant
        if isinstance(capabilities, list) and len(capabilities) > 0:
            payload["capabilities"] = capabilities
        if isinstance(policies, dict) and len(policies) > 0:
            payload["policies"] = policies
        if isinstance(tooling, dict) and len(tooling) > 0:
            payload["tooling"] = tooling
        if isinstance(catalog, dict) and len(catalog) > 0:
            payload["catalog"] = catalog

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
    variant = serializers.CharField(required=False, allow_null=True)
    capabilities = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)
    policies = serializers.DictField(required=False)
    tooling = serializers.DictField(required=False)
    catalog = serializers.DictField(required=False)

    def to_representation(self, obj):
        project_uuid = self.context.get("project_uuid")
        system = self.context.get("system")
        mcp_name = self.context.get("mcp")
        from nexus.inline_agents.models import AgentSystem

        available_systems = list(
            AgentSystem.objects.filter(agents__uuid=obj.uuid).values_list("slug", flat=True).distinct()
        )
        selected_system = system or (available_systems[0] if available_systems else "")
        assigned = False
        if project_uuid:
            assigned = IntegratedAgent.objects.filter(project__uuid=project_uuid, agent=obj).exists()

        from nexus.inline_agents.api.views import (
            _sort_mcps,
            get_all_mcps_for_group,
            get_credentials_for_mcp,
            get_mcps_for_agent_system,
        )

        group_name = obj.group.slug if getattr(obj, "group", None) else None
        if group_name:
            all_group_mcps = get_all_mcps_for_group(group_name)
            system_mcps = all_group_mcps.get(selected_system, []) if selected_system else []
        else:
            system_mcps = get_mcps_for_agent_system(obj.slug, selected_system) if selected_system else []

        if mcp_name and system_mcps:
            selected_mcp = next((mcp for mcp in system_mcps if mcp.get("name") == mcp_name), None)
            if selected_mcp:
                creds = get_credentials_for_mcp(obj.slug, selected_system, mcp_name, group_slug=group_name)
                selected_mcp["credentials"] = creds
            else:
                creds = []
                selected_mcp = {}
        else:
            if system_mcps:
                for mcp in system_mcps:
                    mcp_name_for_creds = mcp.get("name")
                    mcp_creds = get_credentials_for_mcp(
                        obj.slug, selected_system, mcp_name_for_creds, group_slug=group_name
                    )
                    mcp["credentials"] = mcp_creds
            selected_mcp = None
            creds = []

        payload = {
            "name": obj.name,
            "description": obj.collaboration_instructions,
            "type": (obj.agent_type.slug if getattr(obj, "agent_type", None) else ""),
            "group": group_name,
            "category": (obj.category.slug if getattr(obj, "category", None) else ""),
            "system": selected_system,
            "systems": available_systems,
            "assigned": assigned,
            "credentials": creds,
        }

        # Add MCPs or single MCP based on whether mcp_name is provided
        if mcp_name and selected_mcp:
            payload["MCP"] = selected_mcp
            payload["selected_mcp"] = mcp_name
        else:
            # Sort MCPs so that 'Default' appears first
            payload["MCPs"] = _sort_mcps(system_mcps)

        variant = getattr(obj, "variant", None)
        capabilities = getattr(obj, "capabilities", [])
        policies = getattr(obj, "policies", {})
        tooling = getattr(obj, "tooling", {})
        catalog = getattr(obj, "catalog", {})

        if variant is not None:
            payload["variant"] = variant
        if isinstance(capabilities, list) and len(capabilities) > 0:
            payload["capabilities"] = capabilities
        if isinstance(policies, dict) and len(policies) > 0:
            payload["policies"] = policies
        if isinstance(tooling, dict) and len(tooling) > 0:
            payload["tooling"] = tooling
        if isinstance(catalog, dict) and len(catalog) > 0:
            payload["catalog"] = catalog

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
