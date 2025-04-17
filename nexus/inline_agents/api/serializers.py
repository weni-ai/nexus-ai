from rest_framework import serializers
from nexus.inline_agents.models import Agent, IntegratedAgent, AgentCredential


class IntegratedAgentSerializer(serializers.ModelSerializer):

    class Meta:
        model = IntegratedAgent
        fields = ['uuid', 'id', 'name', 'skills', 'is_official', 'description']

    uuid = serializers.UUIDField(source='agent.uuid')
    name = serializers.SerializerMethodField('get_name')
    id = serializers.SerializerMethodField('get_id')
    skills = serializers.SerializerMethodField("get_skills")
    description = serializers.SerializerMethodField("get_description")
    is_official = serializers.SerializerMethodField("get_is_official")

    def get_id(self, obj):
        return obj.agent.slug

    def get_name(self, obj):
        return obj.agent.name

    def get_description(self, obj):
        return obj.agent.collaboration_instructions

    def get_skills(self, obj):
        display_skills = obj.agent.current_version.display_skills
        return display_skills

    def get_is_official(self, obj):
        return obj.agent.is_official

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

    description = serializers.CharField(source='collaboration_instructions')
    model = serializers.CharField(source='foundation_model')
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
        fields = [
            "name",
            "label",
            "placeholder",
            "is_confidential",
            "value",
            "agents_using"
        ]

    def get_agents_using(self, obj):
        return [
            {
                "uuid": agent.uuid,
                "name": agent.name,
            }
            for agent in obj.agents.filter(project=obj.project)
        ]
    
    def get_value(self, obj):
        if obj.is_confidential:
            return obj.value
        return obj.decrypted_value
