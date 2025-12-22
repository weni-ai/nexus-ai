from unittest.mock import MagicMock

from router.classifiers.classification import Classification
from router.entities import Message


def test_non_custom_actions_route_triggers_attachment_flow():
    flows_repo = MagicMock()
    flows_repo.get_classifier_flow_by_action_type.return_value = MagicMock(uuid="f", name="n")
    msg = Message(project_uuid="p", text="t", contact_urn="u", attachments=["file"], metadata={})
    flow_start = MagicMock()
    c = Classification(flows_repository=flows_repo, message=msg, msg_event={}, flow_start=flow_start, user_email="user")
    started = c.non_custom_actions_route()
    assert started is True
    flow_start.start_flow.assert_called_once()
