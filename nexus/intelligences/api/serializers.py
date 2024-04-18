from rest_framework import serializers
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
)
from nexus.task_managers.models import (
    ContentBaseFileTaskManager,
    ContentBaseLinkTaskManager,
)


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
        fields = ["file", "extension_file", "uuid", "created_file_name", "status", "file_name"]

    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        try:
            task_manager = obj.upload_tasks.get()
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
        fields = ["uuid", "link", "status"]

    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        try:
            task_manager = obj.upload_tasks.get()
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


class ContentBasePersonalizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = ["agent", "instructions"]

    agent = ContentBaseAgentSerializer()
    instructions = serializers.SerializerMethodField('get_instructions')

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

    def update(self, instance, validated_data):
        agent_data = validated_data.get("agent")
        if agent_data:

            agent = instance.agent
            agent.name = agent_data.get("name", agent.name)
            agent.role = agent_data.get("role", agent.role)
            agent.personality = agent_data.get("personality", agent.personality)
            agent.goal = agent_data.get("goal", agent.goal)
            agent.save()

        instructions_data = self.context.get('request').data.get('instructions')
        if instructions_data:
            for instruction_data in instructions_data:
                serializer = ContentBaseInstructionSerializer(data=instruction_data, partial=True)
                if serializer.is_valid():
                    if instruction_data.get('id'):
                        instruction = instance.instructions.get(id=instruction_data.get('id'))
                        instruction.instruction = instruction_data.get('instruction')
                        instruction.save()
                        instruction.refresh_from_db()
                    else:
                        instance.instructions.create(instruction=instruction_data.get('instruction'))
        instance.refresh_from_db()
        return instance
