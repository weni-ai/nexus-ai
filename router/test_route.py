from unittest.mock import MagicMock

from router.entities import LLMSetupDTO, Message
from router.route import route


def test_route_fallback_dispatches_direct_message_when_no_flow():
    content_repo = MagicMock()
    content_repo.get_content_base_by_project.return_value = MagicMock(uuid="cb")
    content_repo.get_agent.return_value = MagicMock(
        name="a",
        role="r",
        personality="p",
        goal="g",
        set_default_if_null=lambda: MagicMock(name="a", role="r", personality="p", goal="g"),
    )
    content_repo.list_instructions.return_value = []

    flows_repo = MagicMock()
    flows_repo.project_flow_fallback.return_value = None

    logs_repo = MagicMock()
    logs_repo.list_cached_messages.return_value = []
    logs_repo.list_last_messages.return_value = []

    indexer = MagicMock()
    indexer.search_data.return_value = {"status": 200, "data": {"response": [{"full_page": "page"}]}}

    llm_client = MagicMock()
    llm_client.prompt = "p"
    llm_client.request_gpt.return_value = {"answers": [{"text": "resp"}]}

    dm = MagicMock()
    fs = MagicMock()

    llm_cfg = LLMSetupDTO(
        model="chatgpt",
        model_version="gpt-4o-mini",
        temperature="0.0",
        top_p="1.0",
        max_tokens="100",
        language="por",
    )
    msg = Message(project_uuid="p", text="t", contact_urn="u")

    # Classification other -> no flow, should dispatch direct_message
    out = route(
        classification="other",
        message=msg,
        content_base_repository=content_repo,
        flows_repository=flows_repo,
        message_logs_repository=logs_repo,
        indexer=indexer,
        llm_client=llm_client,
        direct_message=dm,
        flow_start=fs,
        llm_config=llm_cfg,
        flows_user_email="user",
        log_usecase=MagicMock(),
        message_log=None,
    )
    dm.send_direct_message.assert_called_once()
