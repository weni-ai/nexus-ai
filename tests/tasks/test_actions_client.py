import os
from unittest.mock import patch

from router.tasks.actions_client import get_action_clients


@patch.dict(os.environ, {"FLOWS_REST_ENDPOINT": "http://e", "FLOWS_INTERNAL_TOKEN": "it"})
def test_get_action_clients_preview_returns_simulators(monkeypatch):
    broadcast, flow_start = get_action_clients(preview=True, multi_agents=False, project_use_components=False)
    assert broadcast is not None and flow_start is not None


@patch.dict(
    os.environ,
    {"FLOWS_REST_ENDPOINT": "http://e", "FLOWS_SEND_MESSAGE_INTERNAL_TOKEN": "smit", "FLOWS_INTERNAL_TOKEN": "it"},
)
def test_get_action_clients_non_preview_components_true_uses_whatsapp_broadcast(settings):
    settings.AGENT_USE_COMPONENTS = True
    broadcast, flow_start = get_action_clients(preview=False, multi_agents=True, project_use_components=True)
    assert broadcast is not None and flow_start is not None


@patch.dict(
    os.environ,
    {"FLOWS_REST_ENDPOINT": "http://e", "FLOWS_SEND_MESSAGE_INTERNAL_TOKEN": "smit", "FLOWS_INTERNAL_TOKEN": "it"},
)
def test_get_action_clients_non_preview_components_false_uses_send_message(settings):
    settings.AGENT_USE_COMPONENTS = False
    broadcast, flow_start = get_action_clients(preview=False, multi_agents=False, project_use_components=False)
    assert broadcast is not None and flow_start is not None
