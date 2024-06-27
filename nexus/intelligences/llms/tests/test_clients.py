import uuid
from typing import List, Dict

from django.test import TestCase
from nexus.intelligences.llms.wenigpt import WeniGPTClient
from nexus.intelligences.llms.exceptions import WeniGPTInvalidVersionError

from router.entities import ContactMessageDTO, AgentDTO
from django.conf import settings


class WenigptClientTestCase(TestCase):
    def setUp(self) -> None:
        self.content_base_uuid = str(uuid.uuid4())
        self.project_uuid = str(uuid.uuid4())

        self.agent_dto = AgentDTO(
            name="AGENT",
            role="ROLE",
            personality="PERSONALITY",
            goal="GOAL",
            content_base_uuid=self.content_base_uuid,
        )
        self.model_version = settings.WENIGPT_GOLFINHO
        self.instructions: List = ["INSTRUCTION 1", "INSTRUCTION 2", "INSTRUCTION 3"]
        self.chunks: List = ["CHUNK I", "CHUNK II", "CHUNK III"]
        self.agent: Dict = self.agent_dto.__dict__
        self.question: str = "USER QUESTION"
        self.client = WeniGPTClient(self.model_version)

    def test(self):
        last_messages = [
            ContactMessageDTO(contact_urn="", text="QUESTION I", llm_respose="ANSWER I", content_base_uuid=self.content_base_uuid, project_uuid=self.project_uuid),
            ContactMessageDTO(contact_urn="", text="QUESTION II", llm_respose="ANSWER II", content_base_uuid=self.content_base_uuid, project_uuid=self.project_uuid),
            ContactMessageDTO(contact_urn="", text="QUESTION III", llm_respose="ANSWER III", content_base_uuid=self.content_base_uuid, project_uuid=self.project_uuid),
            ContactMessageDTO(contact_urn="", text="QUESTION IV", llm_respose="ANSWER IV", content_base_uuid=self.content_base_uuid, project_uuid=self.project_uuid),
            ContactMessageDTO(contact_urn="", text="QUESTION V", llm_respose="ANSWER V", content_base_uuid=self.content_base_uuid, project_uuid=self.project_uuid),
        ]
        prompt = self.client.format_prompt(self.instructions, self.chunks, self.agent, self.question, last_messages)
        assert "{{" not in prompt
        assert "}}" not in prompt

    def test_url(self):
        self.assertEquals(self.client.url, settings.WENIGPT_API_URL)
        self.client = WeniGPTClient(settings.WENIGPT_SHARK)
        self.assertEquals(self.client.url, settings.WENIGPT_SHARK_API_URL)
        self.client = WeniGPTClient(settings.WENIGPT_TEST)
        self.assertEquals(self.client.url, settings.WENIGPT_TEST_API_URL)

    def test_fail(self):
        with self.assertRaises(WeniGPTInvalidVersionError):
            WeniGPTClient("boto")

    def test_golfinho_prompts(self):
        client = WeniGPTClient(settings.WENIGPT_GOLFINHO)
        self.assertEquals(client.prompt_with_context, settings.WENIGPT_CONTEXT_PROMPT)
        self.assertEquals(client.prompt_without_context, settings.WENIGPT_NO_CONTEXT_PROMPT)
        self.assertEquals(client.pairs_template_prompt, settings.WENIGPT_PAIRS_TEMPLATE_PROMPT)
        self.assertEquals(client.next_question_template_prompt, settings.WENIGPT_NEXT_QUESTION_TEMPLATE_PROMPT)

    def test_shark_prompts(self):
        client = WeniGPTClient(settings.WENIGPT_SHARK)
        self.assertEquals(client.prompt_with_context, settings.WENIGPT_SHARK_CONTEXT_PROMPT)
        self.assertEquals(client.prompt_without_context, settings.WENIGPT_SHARK_NO_CONTEXT_PROMPT)
        self.assertEquals(client.pairs_template_prompt, settings.WENIGPT_SHARK_PAIRS_TEMPLATE_PROMPT)
        self.assertEquals(client.next_question_template_prompt, settings.WENIGPT_SHARK_NEXT_QUESTION_TEMPLATE_PROMPT)

    def test_wenigpt_test_prompts(self):
        client = WeniGPTClient(settings.WENIGPT_SHARK)
        self.assertEquals(client.prompt_with_context, settings.WENIGPT_TEST_CONTEXT_PROMPT)
        self.assertEquals(client.prompt_without_context, settings.WENIGPT_TEST_NO_CONTEXT_PROMPT)
        self.assertEquals(client.pairs_template_prompt, settings.WENIGPT_TEST_PAIRS_TEMPLATE_PROMPT)
        self.assertEquals(client.next_question_template_prompt, settings.WENIGPT_TEST_NEXT_QUESTION_TEMPLATE_PROMPT)
