from unittest.mock import MagicMock

from router.entities import AgentDTO, ContactMessageDTO, InstructionDTO, LLMSetupDTO, Message
from router.llms.call import call_llm


def test_call_llm_success_path_returns_first_answer_text(settings):
    settings.OPENAI_API_KEY = "key"
    llm_model = MagicMock()
    llm_model.request_gpt.return_value = {"answers": [{"text": "hi"}]}
    msg = Message(project_uuid="p", text="q", contact_urn="u")
    agent = AgentDTO(name="a", role="r", personality="p", goal="g", content_base_uuid="cb")
    instructions = [InstructionDTO(instruction="i", content_base_uuid="cb")]
    cfg = LLMSetupDTO(
        model="chatgpt",
        model_version="gpt-4o-mini",
        temperature="0.0",
        top_p="1.0",
        max_tokens="100",
        language="por",
    )
    last_messages = [
        ContactMessageDTO(contact_urn="u", text="t", llm_respose="", content_base_uuid="cb", project_uuid="p")
    ]
    out = call_llm(["c1"], llm_model, msg, agent, instructions, cfg, last_messages, project_uuid="prj")
    assert out == "hi"
