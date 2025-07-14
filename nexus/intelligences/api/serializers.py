from rest_framework import serializers

from nexus.events import event_manager
from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseLogs,
    LLM,
    ContentBaseInstruction,
    ContentBaseAgent,
    Topics,
    SubTopics,
)
from nexus.agents.models import Team
from nexus.projects.models import Project
from nexus.task_managers.models import (
    ContentBaseFileTaskManager,
    ContentBaseLinkTaskManager,
)

from django.forms.models import model_to_dict


class IntelligenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intelligence
        fields = ['name', 'uuid', 'content_bases_count', 'description', 'is_router']


class ContentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = ['uuid', 'title', 'description', 'language', 'is_router']


class RouterContentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = '__all__'


class ContentBaseTextSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseText
        fields = ['text', 'uuid']


class ContentBaseFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseFile
        fields = ["file", "extension_file", "uuid", "created_file_name", "status", "file_name", "created_at"]

    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        try:
            task_manager = obj.upload_tasks.order_by("created_at").last()
            return task_manager.status
        except Exception:
            return ContentBaseFileTaskManager.STATUS_FAIL


class CreatedContentBaseLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseLink
        fields = ["uuid", "link"]


class ContentBaseLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseLink
        fields = ["uuid", "link", "status", "created_at"]

    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        try:
            task_manager = obj.upload_tasks.order_by("created_at").last()
            return task_manager.status
        except Exception as e:
            print(e)
            return ContentBaseLinkTaskManager.STATUS_FAIL


class ContentBaseLogsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseLogs
        fields = [
            "question",
            "language",
            "texts_chunks",
            "full_prompt",
            "weni_gpt_response",
            "wenigpt_version",
            "testing",
            "feedback",
            "correct_answer",
        ]


class LLMConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = LLM
        fields = [
            "uuid",
            "model",
            "setup",
            "advanced_options",
        ]


class ContentBaseInstructionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseInstruction
        fields = ['instruction']


class ContentBaseAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseAgent
        fields = ["name", "role", "personality", "goal"]


class TeamHumanSupportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['human_support', 'human_support_prompt']


class ContentBasePersonalizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = ["agent", "instructions", "team"]

    agent = ContentBaseAgentSerializer()
    instructions = serializers.SerializerMethodField('get_instructions')
    team = serializers.SerializerMethodField('get_team')

    def get_instructions(self, obj):
        instructions = []
        for instruction in obj.instructions.all():
            instructions.append(
                {
                    "id": instruction.id,
                    "instruction": instruction.instruction,
                }
            )
        return instructions

    def get_team(self, obj):

        project_uuid = self.context.get('project_uuid')
        if not project_uuid:
            try:
                project_uuid = str(obj.intelligence.project.uuid)
            except AttributeError:
                return None

        try:
            # TODO: Change to Project data after inline update.
            team = Team.objects.get(project__uuid=project_uuid)
            return {
                'human_support': team.human_support,
                'human_support_prompt': team.human_support_prompt
            }
        except Team.DoesNotExist:
            project = Project.objects.get(uuid=project_uuid)
            return {
                'human_support': project.human_support,
                'human_support_prompt': project.human_support_prompt
            }

    def update(self, instance, validated_data):
        agent_data = validated_data.get("agent")
        instructions_data = self.context.get('request').data.get('instructions')
        team_data = self.context.get('request').data.get('team')
        project_uuid = self.context.get('project_uuid')

        # Handle team human support update if data and project_uuid are provided
        if team_data and project_uuid:
            try:
                team = Team.objects.get(project__uuid=project_uuid)
                project = team.project
                old_human_support = team.human_support

                # Update team data
                team.human_support = team_data.get('human_support', team.human_support)
                team.human_support_prompt = team_data.get('human_support_prompt', team.human_support_prompt)
                team.save()

                project.human_support = team.human_support
                project.human_support_prompt = team.human_support_prompt
                project.save()

                # Only trigger add/rollback if human_support boolean changed
                if old_human_support != team.human_support:
                    from nexus.usecases.agents.agents import AgentUsecase
                    agent_usecase = AgentUsecase()

                    if team.human_support:
                        agent_usecase.add_human_support_to_team(team=team, user=self.context.get('request').user)
                    else:
                        agent_usecase.rollback_human_support_to_team(team=team, user=self.context.get('request').user)

            except Team.DoesNotExist:
                project = Project.objects.get(uuid=project_uuid)
                project.human_support = team_data.get('human_support', project.human_support)
                project.human_support_prompt = team_data.get('human_support_prompt', project.human_support_prompt)
                project.save()

        # Handle agent updates
        if agent_data:
            try:
                agent = instance.agent
                old_agent_data = model_to_dict(agent)

                agent.name = agent_data.get("name", agent.name)
                agent.role = agent_data.get("role", agent.role)
                agent.personality = agent_data.get("personality", agent.personality)
                agent.goal = agent_data.get("goal", agent.goal)
                agent.save()
                new_agent_data = model_to_dict(agent)

                event_manager.notify(
                    event="contentbase_agent_activity",
                    content_base_agent=agent,
                    action_type="U",
                    old_agent_data=old_agent_data,
                    new_agent_data=new_agent_data,
                    user=self.context.get('request').user
                )
            except ContentBaseAgent.DoesNotExist:
                ContentBaseAgent.objects.create(
                    name=agent_data.get("name"),
                    role=agent_data.get("role"),
                    personality=agent_data.get("personality"),
                    goal=agent_data.get("goal"),
                    content_base=instance,
                )

        # Handle instructions updates
        if instructions_data:
            for instruction_data in instructions_data:
                serializer = ContentBaseInstructionSerializer(data=instruction_data, partial=True)
                if serializer.is_valid():
                    if instruction_data.get('id'):
                        instruction = instance.instructions.get(id=instruction_data.get('id'))
                        old_instruction_data = model_to_dict(instruction)

                        instruction.instruction = instruction_data.get('instruction')
                        instruction.save()
                        instruction.refresh_from_db()

                        new_instruction_data = model_to_dict(instruction)
                        event_manager.notify(
                            event="contentbase_instruction_activity",
                            content_base_instruction=instruction,
                            action_type="U",
                            old_instruction_data=old_instruction_data,
                            new_instruction_data=new_instruction_data,
                            user=self.context.get('request').user
                        )
                    else:

                        created_instruction = instance.instructions.create(instruction=instruction_data.get('instruction'))
                        event_manager.notify(
                            event="contentbase_instruction_activity",
                            content_base_instruction=created_instruction,
                            action_type="C",
                            action_details={
                                "old": "",
                                "new": instruction_data.get('instruction')
                            },
                            user=self.context.get('request').user
                        )

        instance.refresh_from_db()
        return instance


class TopicsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topics
        fields = ['name', 'uuid', 'created_at', 'description', 'subtopic']

    subtopic = serializers.SerializerMethodField()

    def get_subtopic(self, obj):
        return SubTopicsSerializer(obj.subtopics.all(), many=True).data


class SubTopicsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubTopics
        fields = ['name', 'uuid', 'created_at', 'description', 'topic_uuid', 'topic_name']

    topic_uuid = serializers.SerializerMethodField()
    topic_name = serializers.SerializerMethodField()

    def get_topic_uuid(self, obj):
        return obj.topic.uuid

    def get_topic_name(self, obj):
        return obj.topic.name


class SupervisorSerializer(serializers.ModelSerializer):
    pass
