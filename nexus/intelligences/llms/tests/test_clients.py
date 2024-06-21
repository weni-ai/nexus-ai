import uuid
from typing import List, Dict

from django.test import TestCase
from nexus.intelligences.llms.wenigpt import WeniGPTClient

from router.entities import ContactMessageDTO, AgentDTO


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
        self.model_version = "runpod"
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
