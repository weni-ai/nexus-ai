import logging
from typing import Dict, List

from router.entities import (
    AgentDTO,
    ContactMessageDTO,
    ContentBaseDTO,
    FlowDTO,
    InstructionDTO,
)
from router.repositories import Repository

logger = logging.getLogger(__name__)


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
            content_base_uuid=content_base_uuid,
        )

    def list_instructions(self, content_base_uuid: str):
        instructions_list = []
        instructions = self.content_base.instructions.all()
        for instruction in instructions:
            instructions_list.append(
                InstructionDTO(
                    instruction=instruction.instruction, content_base_uuid=str(instruction.content_base.uuid)
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
                    content_base_uuid=self.content_base_uuid,
                )
            )
        return messages

    def list_cached_messages(self, project_uuid: str, contact_urn: str):
        return self.list_last_messages(contact_urn, project_uuid, 5)


class FlowsTestRepository(Repository):
    def __init__(self, flow, fallback_flow) -> None:
        self.flow = flow
        self.fallback_flow = fallback_flow

    def get_project_flow_by_name(self, name: str) -> FlowDTO:
        return FlowDTO(
            pk=str(self.flow.uuid),
            uuid=str(self.flow.flow_uuid),
            name=self.flow.name,
            fallback=self.flow.fallback,
            content_base_uuid=str(self.flow.content_base.uuid),
            prompt=self.flow.prompt,
        )

    def project_flow_fallback(self, fallback: bool) -> FlowDTO:
        if self.fallback_flow:
            return FlowDTO(
                pk=str(self.flow.uuid),
                uuid=str(self.fallback_flow.flow_uuid),
                name=self.fallback_flow.name,
                fallback=self.fallback_flow.fallback,
                content_base_uuid=str(self.fallback_flow.content_base.uuid),
                prompt=self.fallback_flow.prompt,
            )
        return


class MockGPTClient:
    prompt = "Prompt: Lorem Ipsum"

    def request_gpt(
        self,
        instructions: List,
        chunks: List,
        agent: Dict,
        question: str,
        llm_config: Dict,
        last_messages: List,
        project_uuid: str = None,
    ):
        return {"answers": [{"text": "LLM Response"}], "id": "0"}


class MockLLMClient:
    @staticmethod
    def get_by_type(type: str):
        types = {
            "chatgpt": MockGPTClient,
            "wenigpt": MockGPTClient,
        }
        return types.get(type)


class MockIndexer:
    def __init__(self, file_uuid: str = None) -> None:
        self.file_uuid = file_uuid

    def search_data(self, content_base_uuid: str = None, text: str = None):
        return {
            "status": 200,
            "data": {
                "response": [
                    {
                        "full_page": "Full page info",
                        "filename": "file.docx",
                        "file_uuid": self.file_uuid,
                    }
                ]
            },
        }


class MockBroadcastHTTPClient:
    def send_direct_message(
        self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict], **kwargs
    ):
        logger.debug("Test: Sending direct message", extra={"urns": urns})


class MockFlowStartHTTPClient:
    def start_flow(self, flow: str, user: str, urns: List, user_message: str, llm_response: str):
        logger.debug("Test: Starting flow", extra={"flow": flow})


class TestException(Exception):
    pass


class MockCacheService:
    """Mock CacheService for testing.

    Uses MockCacheRepository internally for in-memory caching.
    Useful for tests that need to verify cache behavior without Redis.
    """

    def __init__(self):
        from router.repositories.mocks import MockCacheRepository
        from router.services.cache_service import CacheService

        mock_repository = MockCacheRepository()
        self.cache_service = CacheService(cache_repository=mock_repository)
        self.repository = mock_repository  # Expose repository for direct inspection

    def __getattr__(self, name):
        """Delegate all method calls to the actual CacheService."""
        return getattr(self.cache_service, name)

    def clear_all(self) -> None:
        """Clear all cache (useful for test teardown)."""
        self.repository.clear()

    def get_cache_keys(self) -> List[str]:
        """Get all cache keys (useful for testing)."""
        return self.repository.get_all_keys()

    def get_cache_size(self) -> int:
        """Get number of cached items (useful for testing)."""
        return len(self.repository.get_all_keys())
