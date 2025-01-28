import emoji

from rest_framework import serializers

from nexus.agents.models import (
    Agent,
    ActiveAgent,
    AgentSkills,
)


class ActiveAgentSerializer(serializers.ModelSerializer):

    class Meta:
        model = ActiveAgent
        fields = ['uuid', 'agent', 'team', 'is_official']


class ActiveAgentTeamSerializer(serializers.ModelSerializer):

    class Meta:
        model = ActiveAgent
        fields = ['uuid', 'name', 'skills', 'is_official', 'external_id']

    name = serializers.SerializerMethodField('get_name')
    skills = serializers.SerializerMethodField("get_skills")
    external_id = serializers.SerializerMethodField("get_external_id")

    def get_name(self, obj):
        return obj.agent.display_name
    
    def get_external_id(self, obj):
        return obj.agent.external_id

    def get_skills(self, obj):
        skills = obj.agent.agent_skills
        return SkillSerializer(skills, many=True).data


class SkillSerializer(serializers.ModelSerializer):

    icon = serializers.SerializerMethodField('get_icon')
    name = serializers.SerializerMethodField('get_name')

    class Meta:
        model = AgentSkills
        fields = [
            "icon",
            "name",
            "unique_name",
            "agent",
            # "skill",
        ]

    def get_name(self, obj):
        s = obj.display_name.split(" ")
        clean_name = " ".join([word for word in s if not emoji.is_emoji(word)])
        return clean_name

    def get_icon(self, obj):
        s = obj.display_name.split(" ")
        icon = " ".join([word for word in s if emoji.is_emoji(word)])
        return icon


class AgentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Agent
        fields = [
            "uuid",
            "name",
            "description",
            "skills",
            "assigned",
            "external_id",
            "slug",
            "model",
            "is_official",
            "project",
            # "metadata",
        ]

    name = serializers.SerializerMethodField('get_name')
    skills = serializers.SerializerMethodField("get_skills")
    assigned = serializers.SerializerMethodField("get_is_assigned")
    # skills = SkillSerializer(read_only=True, source="agent_skills")

    def get_name(self, obj):
        return obj.display_name

    def get_skills(self, obj):
        skills = obj.agent_skills
        return SkillSerializer(skills, many=True).data

    def get_is_assigned(self, obj):
        project_uuid = self.context.get("project_uuid")
        active_agent = ActiveAgent.objects.filter(team__project__uuid=project_uuid, agent=obj)
        return active_agent.exists()
