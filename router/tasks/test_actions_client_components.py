import os
from unittest.mock import patch

from router.tasks.actions_client import get_action_clients


@patch.dict(os.environ, {"FLOWS_REST_ENDPOINT": "http://e", "FLOWS_INTERNAL_TOKEN": "it"})
def test_get_action_clients_preview_components_true(monkeypatch):
    broadcast, flow_start = get_action_clients(preview=True, multi_agents=False, project_use_components=True)
    assert broadcast is not None and flow_start is not None
