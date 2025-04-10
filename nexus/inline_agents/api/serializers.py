from rest_framework import serializers
from nexus.inline_agents.models import Agent, IntegratedAgent


class IntegratedAgentSerializer(serializers.ModelSerializer):

    class Meta:
        model = IntegratedAgent
        fields = ['uuid', 'name', 'skills', 'is_official', 'description']

    uuid = serializers.UUIDField(source='agent.uuid')
    name = serializers.SerializerMethodField('get_name')
    skills = serializers.SerializerMethodField("get_skills")
    description = serializers.SerializerMethodField("get_description")
    is_official = serializers.SerializerMethodField("get_is_official")

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
        # TODO: Implement credentials
        return []
