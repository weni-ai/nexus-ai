import emoji

from rest_framework import serializers

from nexus.agents.models import (
    Agent,
    ActiveAgent,
    AgentSkills,
    Credential,
    AgentMessage,
)


class ActiveAgentSerializer(serializers.ModelSerializer):

    class Meta:
        model = ActiveAgent
        fields = ['uuid', 'agent', 'team', 'is_official']


class ActiveAgentTeamSerializer(serializers.ModelSerializer):

    class Meta:
        model = ActiveAgent
        fields = ['uuid', 'name', 'skills', 'is_official', 'external_id', 'description']

    name = serializers.SerializerMethodField('get_name')
    skills = serializers.SerializerMethodField("get_skills")
    external_id = serializers.SerializerMethodField("get_external_id")
    description = serializers.SerializerMethodField("get_description")

    def get_name(self, obj):
        return obj.agent.display_name

    def get_external_id(self, obj):
        return obj.agent.external_id

    def get_description(self, obj):
        return obj.agent.description

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
            "credentials",
            # "metadata",
        ]

    name = serializers.SerializerMethodField('get_name')
    skills = serializers.SerializerMethodField("get_skills")
    assigned = serializers.SerializerMethodField("get_is_assigned")
    credentials = serializers.SerializerMethodField("get_credentials")
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

    def get_credentials(self, obj):
        credentials = obj.credential_set.all().distinct("label")
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
    name = serializers.SerializerMethodField("get_name")
    value = serializers.SerializerMethodField("get_value")

    class Meta:
        model = Credential
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
                "name": agent.display_name,
            }
            for agent in obj.agents.filter(active_agents__team=obj.project.team)
        ]

    def get_name(self, obj):
        return obj.key

    def get_value(self, obj):
        if obj.is_confidential:
            return obj.value
        return obj.decrypted_value


class AgentMessageHistorySerializer(serializers.ModelSerializer):

    class Meta:
        model = AgentMessage
        fields = [
            'id',
            'created_at',
            'message_text',
            'tag',
            'classification',
        ]

    message_text = serializers.SerializerMethodField()
    tag = serializers.SerializerMethodField()
    classification = serializers.SerializerMethodField()

    def get_message_text(self, obj):
        return obj.user_text

    def get_tag(self, obj):
        return "S"

    def get_classification(self, obj):
        return "other"


class AgentMessageDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentMessage
        fields = [
            "id",
            "uuid",
            "text",
            "status",
            "llm_response",
            "groundedness",
            "contact_urn",
            "actions_started",
            "actions_uuid",
            "actions_type",
            "is_approved",
        ]

    text = serializers.SerializerMethodField()
    llm_response = serializers.SerializerMethodField()
    groundedness = serializers.SerializerMethodField()
    actions_started = serializers.SerializerMethodField()
    actions_type = serializers.SerializerMethodField()
    actions_uuid = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    is_approved = serializers.SerializerMethodField()

    def get_text(self, obj):
        return obj.user_text
        return obj.response_status

    def get_llm_response(self, obj):
        return obj.agent_response

    def get_groundedness(self, obj) -> str | None:
        return None

    def get_actions_started(self, obj):
        return False

    def get_actions_type(self, obj):
        return "other"

    def get_actions_uuid(self, obj):
        return None

    def get_status(self, obj):
        return "S"

    def get_is_approved(self, obj):
        return True
