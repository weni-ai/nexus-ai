import logging

from django.forms.models import model_to_dict
from rest_framework import serializers

from nexus.agents.models import Team
from nexus.events import event_manager, notify_async
from nexus.intelligences.models import (
    LLM,
    ContentBase,
    ContentBaseAgent,
    ContentBaseFile,
    ContentBaseInstruction,
    ContentBaseLink,
    ContentBaseLogs,
    ContentBaseText,
    Conversation,
    Intelligence,
    SubTopics,
    Topics,
)
from nexus.projects.models import Project
from nexus.task_managers.models import (
    ContentBaseFileTaskManager,
    ContentBaseLinkTaskManager,
)

logger = logging.getLogger(__name__)


class IntelligenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intelligence
        fields = ["name", "uuid", "content_bases_count", "description", "is_router"]


class ContentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = ["uuid", "title", "description", "language", "is_router"]


class RouterContentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = "__all__"


class ContentBaseTextSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseText
        fields = ["text", "uuid"]


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
            logger.error("Serializer exception: %s", e, exc_info=True)
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
        fields = ["instruction"]


class ContentBaseAgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseAgent
        fields = ["name", "role", "personality", "goal"]


class TeamHumanSupportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ["human_support", "human_support_prompt"]


class ContentBasePersonalizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = ["agent", "instructions", "team"]

    agent = ContentBaseAgentSerializer()
    instructions = serializers.SerializerMethodField("get_instructions")
    team = serializers.SerializerMethodField("get_team")

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
        project_uuid = self.context.get("project_uuid")
        if not project_uuid:
            try:
                project_uuid = str(obj.intelligence.project.uuid)
            except AttributeError:
                return None

        try:
            # TODO: Change to Project data after inline update.
            team = Team.objects.get(project__uuid=project_uuid)
            return {"human_support": team.human_support, "human_support_prompt": team.human_support_prompt}
        except Team.DoesNotExist:
            project = Project.objects.get(uuid=project_uuid)
            return {"human_support": project.human_support, "human_support_prompt": project.human_support_prompt}

    def update(self, instance, validated_data):
        agent_data = validated_data.get("agent")
        instructions_data = self.context.get("request").data.get("instructions")
        team_data = self.context.get("request").data.get("team")
        project_uuid = self.context.get("project_uuid")

        # Handle team human support update if data and project_uuid are provided
        if team_data and project_uuid:
            try:
                team = Team.objects.get(project__uuid=project_uuid)
                project = team.project
                old_human_support = team.human_support

                # Update team data
                team.human_support = team_data.get("human_support", team.human_support)
                team.human_support_prompt = team_data.get("human_support_prompt", team.human_support_prompt)
                team.save()

                project.human_support = team.human_support
                project.human_support_prompt = team.human_support_prompt
                project.save()

                # Fire cache invalidation event for team update (async observer)
                notify_async(
                    event="cache_invalidation:team",
                    project_uuid=project_uuid,
                )

                # Only trigger add/rollback if human_support boolean changed
                if old_human_support != team.human_support:
                    from nexus.usecases.agents.agents import AgentUsecase

                    agent_usecase = AgentUsecase()

                    if team.human_support:
                        agent_usecase.add_human_support_to_team(team=team, user=self.context.get("request").user)
                    else:
                        agent_usecase.rollback_human_support_to_team(team=team, user=self.context.get("request").user)

            except Team.DoesNotExist:
                project = Project.objects.get(uuid=project_uuid)
                project.human_support = team_data.get("human_support", project.human_support)
                project.human_support_prompt = team_data.get("human_support_prompt", project.human_support_prompt)
                project.save()

                # Fire cache invalidation event for team update
                event_manager.notify(
                    event="cache_invalidation:team",
                    project_uuid=project_uuid,
                )

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
                    user=self.context.get("request").user,
                )

                # Fire cache invalidation event
                try:
                    project_uuid = str(instance.intelligence.project.uuid)
                    notify_async(
                        event="cache_invalidation:content_base_agent",
                        content_base_agent=agent,
                        project_uuid=project_uuid,
                    )
                except AttributeError:
                    pass  # Skip if no project
            except ContentBaseAgent.DoesNotExist:
                created_agent = ContentBaseAgent.objects.create(
                    name=agent_data.get("name"),
                    role=agent_data.get("role"),
                    personality=agent_data.get("personality"),
                    goal=agent_data.get("goal"),
                    content_base=instance,
                )

                # Fire cache invalidation event for agent creation
                try:
                    project_uuid = str(instance.intelligence.project.uuid)
                    notify_async(
                        event="cache_invalidation:content_base_agent",
                        content_base_agent=created_agent,
                        project_uuid=project_uuid,
                    )
                except AttributeError:
                    pass  # Skip if no project

        # Handle instructions updates
        if instructions_data:
            for instruction_data in instructions_data:
                serializer = ContentBaseInstructionSerializer(data=instruction_data, partial=True)
                if serializer.is_valid():
                    if instruction_data.get("id"):
                        instruction = instance.instructions.get(id=instruction_data.get("id"))
                        old_instruction_data = model_to_dict(instruction)

                        instruction.instruction = instruction_data.get("instruction")
                        instruction.save()
                        instruction.refresh_from_db()

                        new_instruction_data = model_to_dict(instruction)
                        event_manager.notify(
                            event="contentbase_instruction_activity",
                            content_base_instruction=instruction,
                            action_type="U",
                            old_instruction_data=old_instruction_data,
                            new_instruction_data=new_instruction_data,
                            user=self.context.get("request").user,
                        )

                        # Fire cache invalidation event
                        try:
                            project_uuid = str(instance.intelligence.project.uuid)
                            notify_async(
                                event="cache_invalidation:content_base_instruction",
                                content_base_instruction=instruction,
                                project_uuid=project_uuid,
                            )
                        except AttributeError:
                            pass  # Skip if no project
                    else:
                        created_instruction = instance.instructions.create(
                            instruction=instruction_data.get("instruction")
                        )
                        event_manager.notify(
                            event="contentbase_instruction_activity",
                            content_base_instruction=created_instruction,
                            action_type="C",
                            action_details={"old": "", "new": instruction_data.get("instruction")},
                            user=self.context.get("request").user,
                        )

                        # Fire cache invalidation event
                        try:
                            project_uuid = str(instance.intelligence.project.uuid)
                            notify_async(
                                event="cache_invalidation:content_base_instruction",
                                content_base_instruction=created_instruction,
                                project_uuid=project_uuid,
                            )
                        except AttributeError:
                            pass  # Skip if no project

        instance.refresh_from_db()
        return instance


class TopicsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topics
        fields = ["name", "uuid", "created_at", "description", "subtopic"]

    subtopic = serializers.SerializerMethodField()

    def get_subtopic(self, obj):
        return SubTopicsSerializer(obj.subtopics.all(), many=True).data


class SubTopicsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubTopics
        fields = ["name", "uuid", "created_at", "description", "topic_uuid", "topic_name"]

    topic_uuid = serializers.SerializerMethodField()
    topic_name = serializers.SerializerMethodField()

    def get_topic_uuid(self, obj):
        return obj.topic.uuid

    def get_topic_name(self, obj):
        return obj.topic.name


class SupervisorDataSerializer(serializers.ModelSerializer):
    """
    Serializer for supervisor data from Conversation model
    """

    created_on = serializers.DateTimeField(source="created_at")
    urn = serializers.CharField(source="contact_urn")
    topic = serializers.CharField(source="topic.name", allow_null=True, allow_blank=True)
    name = serializers.CharField(source="contact_name", allow_null=True, allow_blank=True)
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()

    class Meta:
        model = Conversation
        fields = [
            "created_on",
            "urn",
            "uuid",
            "external_id",
            "csat",
            "nps",
            "topic",
            "has_chats_room",
            "start_date",
            "end_date",
            "resolution",
            "name",
        ]

    def to_representation(self, instance):
        """Custom representation to handle resolution and csat fields properly"""
        data = super().to_representation(instance)

        # Handle resolution field - convert tuple string to actual value
        resolution_value = data.get("resolution")
        if resolution_value is not None:
            if isinstance(resolution_value, str) and resolution_value.startswith("("):
                # Extract the actual value from tuple string like "(0, 'Resolved')"
                try:
                    import ast

                    resolution_tuple = ast.literal_eval(resolution_value)
                    data["resolution"] = str(resolution_tuple[0])  # Use the numeric value
                except (ValueError, SyntaxError):
                    pass
            elif isinstance(resolution_value, int):
                # Convert integer to string (database stores integers)
                data["resolution"] = str(resolution_value)

        # Handle csat field - convert tuple string to actual value and ensure it's a string
        csat_value = data.get("csat")
        if csat_value:
            if isinstance(csat_value, str) and csat_value.startswith("("):
                # Extract the actual value from tuple string like "(4, 'Very unsatisfied')"
                try:
                    import ast

                    csat_tuple = ast.literal_eval(csat_value)
                    data["csat"] = str(csat_tuple[0])  # Use the numeric value
                except (ValueError, SyntaxError):
                    pass
            elif isinstance(csat_value, int):
                # Convert integer to string
                data["csat"] = str(csat_value)

        return data


class InstructionClassificationRequestSerializer(serializers.Serializer):
    """
    Serializer for instruction classification request body
    """

    instruction = serializers.CharField(
        required=True,
        help_text=("Instruction text to classify against existing content base instructions."),
    )
    language = serializers.CharField(
        required=True,
        help_text=("Language code for classification context (e.g., pt-br, en, es)."),
    )


class ClassificationItemSerializer(serializers.Serializer):
    """
    Serializer for a single classification item
    """

    name = serializers.CharField(help_text="The classification category or type assigned to the instruction")
    reason = serializers.CharField(
        required=False, allow_blank=True, help_text="The reason or explanation for this classification"
    )


class InstructionClassificationResponseSerializer(serializers.Serializer):
    """
    Serializer for instruction classification response
    """

    classification = ClassificationItemSerializer(
        many=True,
        help_text="Classifications for the instruction; each has category and optional reason.",
    )
    suggestion = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional suggestion to improve or modify the instruction",
    )
