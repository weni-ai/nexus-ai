from unittest.mock import MagicMock

from router.entities.intelligences import AgentDTO, InstructionDTO, LLMSetupDTO
from router.entities.logs import ContactMessageDTO
from router.entities.mailroom import Message
from router.llms.call import call_llm


def test_call_llm_happy_path():
    llm_client = MagicMock()
    llm_client.request_gpt.return_value = {"answers": [{"text": "resp"}]}
    msg = Message(project_uuid="p", text="q", contact_urn="u")
    agent = AgentDTO(name="a", role="r", personality="p", goal="g", content_base_uuid="cb")
    instructions = [InstructionDTO(instruction="i", content_base_uuid="cb")]
    llm_cfg = LLMSetupDTO(model="chatgpt", model_version="gpt-4o-mini", temperature="0", top_p="1", max_tokens="100")
    last_msgs = [ContactMessageDTO(text="t", contact_urn="u", llm_respose="", content_base_uuid="cb", project_uuid="p")]
    out = call_llm(["chunk"], llm_client, msg, agent, instructions, llm_cfg, last_msgs, project_uuid="p")
    assert out == "resp"


def test_call_llm_token_limit_fallback(monkeypatch):
    from nexus.intelligences.llms.client import LLMClient

    class DummyLLM:
        def __init__(self, *args, **kwargs):
            pass

        def request_gpt(self, **kwargs):
            return {"answers": [{"text": "resp2"}]}

    llm_client = MagicMock()

    class TokenLimitError(Exception):
        pass

    # Simulate TokenLimitError
    # Make the llm_client raise the project's TokenLimitError directly
    from nexus.intelligences.llms.exceptions import TokenLimitError as ProjectTokenLimitError

    llm_client.request_gpt.side_effect = ProjectTokenLimitError()

    # Patch LLMClient.get_by_type to return DummyLLM
    monkeypatch.setattr(LLMClient, "get_by_type", staticmethod(lambda t: [lambda **kw: DummyLLM()]))

    msg = Message(project_uuid="p", text="q", contact_urn="u")
    agent = AgentDTO(name="a", role="r", personality="p", goal="g", content_base_uuid="cb")
    instructions = [InstructionDTO(instruction="i", content_base_uuid="cb")]
    llm_cfg = LLMSetupDTO(model="chatgpt", model_version="gpt-4o-mini", temperature="0", top_p="1", max_tokens="100")
    last_msgs = [ContactMessageDTO(text="t", contact_urn="u", llm_respose="", content_base_uuid="cb", project_uuid="p")]
    out = call_llm(["chunk"], llm_client, msg, agent, instructions, llm_cfg, last_msgs, project_uuid="p")
    assert out == "resp2"
