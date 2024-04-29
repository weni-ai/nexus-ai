from typing import List, Dict

from router.repositories import Repository
from router.entities import (
    AgentDTO,
    InstructionDTO,
    FlowDTO,
    ContentBaseDTO,
    ContactMessageDTO,
)

class ContentBaseTestRepository(Repository):
    def __init__(self, content_base, agent) -> None:
        self.agent = agent
        self.content_base = content_base

    def get_content_base_by_project(self, project_uuid):
        return ContentBaseDTO(
            uuid=str(self.content_base.uuid),
            title=self.content_base.title,
            intelligence_uuid=str(self.content_base.intelligence.uuid),
        )

    def get_agent(self, content_base_uuid: str):
        return AgentDTO(
            name=self.agent.name,
            role=self.agent.role,
            personality=self.agent.personality,
            goal=self.agent.goal,
            content_base_uuid=content_base_uuid
        )
    
    def list_instructions(self, content_base_uuid: str):
        instructions_list = []
        instructions = self.content_base.instructions.all()
        for instruction in instructions:
            instructions_list.append(
                InstructionDTO(
                    instruction=instruction.instruction,
                    content_base_uuid=str(instruction.content_base.uuid)
                )
            )

        return instructions_list


class MessageLogsTestRepository(Repository):
    def __init__(self, content_base_uuid: str) -> None:
        self.content_base_uuid = content_base_uuid
    def list_last_messages(self, contact_urn: str, project_uuid: str, number_of_messages: int):
        messages = []
        for i in range(number_of_messages):
            messages.append(
                ContactMessageDTO(
                    text=f"Text {i}",
                    contact_urn=contact_urn,
                    llm_respose=f"Response {i}",
                    project_uuid=project_uuid,
                    content_base_uuid=self.content_base_uuid
                )
            )
        return messages


class FlowsTestRepository(Repository):

    def __init__(self, flow, fallback_flow) -> None:
        self.flow = flow
        self.fallback_flow = fallback_flow

    def get_project_flow_by_name(self, project_uuid: str, name: str) -> FlowDTO:
        return FlowDTO(
            uuid=str(self.flow.uuid),
            name=self.flow.name,
            fallback=self.flow.fallback,
            content_base_uuid=str(self.flow.content_base),
            prompt=self.flow.prompt,
        )

    def project_flow_fallback(self, project_uuid: str, fallback: bool) -> FlowDTO:
        if self.fallback_flow:
            return FlowDTO(
                uuid=str(self.fallback_flow.uuid),
                name=self.fallback_flow.name,
                fallback=self.fallback_flow.fallback,
                content_base_uuid=str(self.fallback_flow.content_base),
                prompt=self.fallback_flow.prompt,
            )
        return

class MockGPTClient:
    prompt = "Prompt: Lorem Ipsum"
    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config: Dict, last_messages: List):
        return {"answers":[{"text": "LLM Response"}],"id":"0"}


class MockLLMClient:
    @staticmethod
    def get_by_type(type: str):
        types = {
            "chatgpt": MockGPTClient,
            "wenigpt": MockGPTClient,
        }
        return types.get(type)


class MockIndexer:
    def search_data(self, content_base_uuid: str, text: str):
        return {
            "status": 200,
            "data": {"response": ["Lorem Ipsum"]}
        }

class MockBroadcastHTTPClient():
    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str):
        print(f"[+ Test: Sending direct message to {urns} +]")


class MockFlowStartHTTPClient():
    def start_flow(self, flow: str, user: str, urns: List, user_message: str):
        print(f"[+ Test: Starting flow {flow} +]")


class TestException(BaseException):
    pass
