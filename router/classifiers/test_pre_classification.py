from unittest.mock import MagicMock

from router.classifiers.pre_classification import PreClassification
from router.entities import Message


def test_pre_classification_route_triggers_safety_or_prompt_guard():
    flows_repo = MagicMock()
    flows_repo.get_classifier_flow_by_action_type.return_value = MagicMock(uuid="f", name="n")
    msg = Message(project_uuid="p", text="t", contact_urn="u", attachments=[], metadata={})
    flow_start = MagicMock()

    # Mock SafeGuard to return unsafe -> should start flow
    with __import__("unittest").mock.patch("router.classifiers.pre_classification.SafeGuard") as SG:
        SG.return_value.classify.return_value = False
        pc = PreClassification(
            flows_repository=flows_repo, message=msg, msg_event={}, flow_start=flow_start, user_email="user"
        )
        started = pc.pre_classification_route()
        assert started is True
        flow_start.start_flow.assert_called_once()


def test_pre_classification_preview_returns_flow_dto_when_unsafe():
    flows_repo = MagicMock()
    flows_repo.get_classifier_flow_by_action_type.return_value = MagicMock(uuid="f", name="n")
    msg = Message(project_uuid="p", text="t", contact_urn="u", attachments=[], metadata={})
    flow_start = MagicMock()

    with __import__("unittest").mock.patch("router.classifiers.pre_classification.SafeGuard") as SG:
        SG.return_value.classify.return_value = False
        pc = PreClassification(
            flows_repository=flows_repo, message=msg, msg_event={}, flow_start=flow_start, user_email="user"
        )
        result = pc.pre_classification(source="preview")
        assert result["type"] == "flowstart"
