from django.test import TestCase

from nexus.usecases.intelligences.tests.intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory,
    ContentBaseFileFactory,
    ContentBaseLinkFactory,
    LLMFactory,
    ContentBaseInstructionFactory,
)
from nexus.intelligences.api.serializers import (
    IntelligenceSerializer,
    ContentBaseSerializer,
    RouterContentBaseSerializer,
    ContentBaseTextSerializer,
    ContentBaseFileSerializer,
    CreatedContentBaseLinkSerializer,
    ContentBaseLinkSerializer,
    ContentBaseLogsSerializer,
    LLMConfigSerializer,
    ContentBaseInstructionSerializer,
    ContentBaseAgentSerializer,
    ContentBasePersonalizationSerializer
)

from nexus.task_managers.models import TaskManager
from nexus.intelligences.models import ContentBaseLogs


class MockRequest:
    def __init__(self, user=None):
        self.data = {"instructions": []}
        self.user = user


class IntelligencesSerializersTestCase(TestCase):
    def setUp(self) -> None:
        self.llm = LLMFactory()
        integrated_intelligence = self.llm.integrated_intelligence
        self.user = integrated_intelligence.created_by

        self.content_base = ContentBaseFactory(
            created_by=self.user,
            intelligence=integrated_intelligence.intelligence
        )
        self.intelligence = IntelligenceFactory()
        self.content_base_text = ContentBaseTextFactory()
        self.content_base_file = ContentBaseFileFactory()
        self.content_base_link = ContentBaseLinkFactory()
        self.content_base_instruction = ContentBaseInstructionFactory()

    def test_intelligence_serializer(self):
        serializer = IntelligenceSerializer(self.intelligence)
        serializer_fields = list(serializer.data.keys())
        fields = ['name', 'uuid', 'content_bases_count', 'description', 'is_router']
        self.assertListEqual(serializer_fields, fields)

    def test_content_base_serializer(self):
        serializer = ContentBaseSerializer(self.content_base)
        serializer_fields = list(serializer.data.keys())
        fields = ['uuid', 'title', 'description', 'language', 'is_router']
        self.assertListEqual(serializer_fields, fields)

    def test_router_content_base_serializer(self):
        serializer = RouterContentBaseSerializer(self.content_base)
        serializer_fields = list(serializer.data.keys())
        fields = ['uuid', 'created_at', 'modified_at', 'is_active', 'title', 'description', 'language', 'is_router', 'created_by', 'modified_by', 'intelligence']
        self.assertListEqual(serializer_fields, fields)

    def test_content_base_text_serializer(self):
        serializer = ContentBaseTextSerializer(self.content_base_text)
        serializer_fields = list(serializer.data.keys())
        fields = ['text', 'uuid']
        self.assertListEqual(serializer_fields, fields)

    def test_content_base_file_serializer_status_exception(self):
        serializer = ContentBaseFileSerializer(self.content_base_file)
        data = serializer.data
        serializer_fields = list(data.keys())
        fields = ["file", "extension_file", "uuid", "created_file_name", "status", "file_name", "created_at"]
        self.assertListEqual(serializer_fields, fields)
        self.assertEqual(data.get("status"), TaskManager.STATUS_FAIL)

    def test_content_base_file_serializer(self):
        content_base_file = ContentBaseFileFactory()
        content_base_file.upload_tasks.create(
            created_by=self.user
        )

        serializer = ContentBaseFileSerializer(content_base_file)
        data = serializer.data

        serializer_fields = list(data.keys())
        fields = ["file", "extension_file", "uuid", "created_file_name", "status", "file_name", "created_at"]
        self.assertListEqual(serializer_fields, fields)
        self.assertEqual(data.get("status"), TaskManager.STATUS_WAITING)

    def test_created_content_base_link_serializer(self):
        serializer = CreatedContentBaseLinkSerializer(self.content_base_link)
        serializer_fields = list(serializer.data.keys())
        fields = ["uuid", "link"]
        self.assertListEqual(serializer_fields, fields)

    def test_content_base_link_serializer_status_exception(self):
        serializer = ContentBaseLinkSerializer(self.content_base_link)
        data = serializer.data
        serializer_fields = list(data.keys())
        fields = ["uuid", "link", "status", "created_at"]
        self.assertListEqual(serializer_fields, fields)
        self.assertEqual(data.get("status"), TaskManager.STATUS_FAIL)

    def test_content_base_link_serializer(self):
        content_base_link = ContentBaseLinkFactory()
        content_base_link.upload_tasks.create(created_by=self.user)

        serializer = ContentBaseLinkSerializer(content_base_link)
        data = serializer.data
        serializer_fields = list(data.keys())
        fields = ["uuid", "link", "status", "created_at"]

        self.assertListEqual(serializer_fields, fields)
        self.assertEqual(data.get("status"), TaskManager.STATUS_WAITING)

    def test_content_base_logs_serializer(self):
        logs = ContentBaseLogs.objects.create(
            question="Test",
            language="en",
            texts_chunks=[],
            full_prompt="",
            weni_gpt_response="",
            wenigpt_version="",
            testing=False,
            user_feedback="",
            correct_answer=True,
        )
        serializer = ContentBaseLogsSerializer(logs)
        serializer_fields = list(serializer.data.keys())
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
        self.assertListEqual(serializer_fields, fields)

    def test_llm_config_serializer(self):
        serializer = LLMConfigSerializer(self.llm)
        serializer_fields = list(serializer.data.keys())
        fields = [
            "uuid",
            "model",
            "setup",
            "advanced_options",
        ]
        self.assertListEqual(serializer_fields, fields)

    def test_content_base_instruction_serializer(self):
        serializer = ContentBaseInstructionSerializer(self.content_base_instruction)
        serializer_fields = list(serializer.data.keys())
        fields = ['instruction']
        self.assertListEqual(serializer_fields, fields)

    def test_content_base_agent_serializer(self):
        content_base_agent = self.content_base.agent
        serializer = ContentBaseAgentSerializer(content_base_agent)
        serializer_fields = list(serializer.data.keys())
        fields = ["name", "role", "personality", "goal"]
        self.assertListEqual(serializer_fields, fields)

    def test_content_base_personalization_serializer(self):
        serializer = ContentBasePersonalizationSerializer(self.content_base)
        serializer_fields = list(serializer.data.keys())
        fields = ["agent", "instructions", "team"]
        instructions = serializer.get_instructions(self.content_base)

        self.assertListEqual(serializer_fields, fields)
        self.assertListEqual(list(instructions[0].keys()), ["id", "instruction"])
        self.assertEqual(len(instructions), 1)

    def test_content_base_personalization_update_serializer(self):
        name = "Updated name"
        data = {
            "agent": {
                "name": name,
                "role": "Updated role",
                "personality": "Updated personality",
                "goal": "Updated goal",
            }
        }
        serializer = ContentBasePersonalizationSerializer(
            self.content_base,
            data=data,
            partial=True,
            context={"request": MockRequest(
                user=self.user
            )}
        )
        instance = serializer.update(self.content_base, validated_data=data)
        self.assertEqual(instance.agent.name, name)

    def test_content_base_personalization_update_serializer_agent_dosent_exist(self):
        self.content_base.agent.delete()
        self.content_base.refresh_from_db()
        name = "Updated name"
        data = {
            "agent": {
                "name": name,
                "role": "Updated role",
                "personality": "Updated personality",
                "goal": "Updated goal",
            }
        }
        request = MockRequest(
            user=self.user
        )
        request.data.update(
            {
                "instructions": [
                    {
                        "id": self.content_base.instructions.first().id,
                        "instruction": "Update"
                    },
                    {
                        "instruction": "Create"
                    }
                ]}
        )
        serializer = ContentBasePersonalizationSerializer(
            self.content_base,
            data=data,
            partial=True,
            context={"request": MockRequest()}
        )
        instance = serializer.update(self.content_base, validated_data=data)
        self.assertEqual(instance.agent.name, name)
