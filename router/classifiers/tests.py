from django.test import TestCase

from router.classifiers.zeroshot import ZeroshotClassifier

from nexus.usecases.actions.tests.flow_factory import FlowFactory
from router.entities.flow import FlowDTO


class mock_zero_shot_client:
    def __init__(self, chatbot_goal, response=None):
        self.chatbot_goal = chatbot_goal
        self.response = response if response is not None else {"other": "other"}

    def fast_predict(self, message, flows_list, language):
        return self.response


class TestZeroshotClassifier(TestCase):

    def setUp(self) -> None:
        self.flow_list = []
        batch_flow_build = FlowFactory.build_batch(3)
        for flow in batch_flow_build:
            self.flow_list.append(FlowDTO(
                uuid=flow.uuid,
                name=flow.name,
                prompt=flow.prompt,
                content_base_uuid=flow.content_base.uuid,
                fallback=flow.fallback
            ))

    def test_predict(self):
        classifier = ZeroshotClassifier(chatbot_goal="test", client=mock_zero_shot_client)
        classification = classifier.predict("test", self.flow_list)
        self.assertEqual(classification, "other")

    def test_predict_with_classification(self):
        classifier = ZeroshotClassifier(chatbot_goal="test", client=mock_zero_shot_client)
        classification = classifier.predict("test", self.flow_list)
        self.assertEqual(classification, "other")

    def test_zeroshotclassifier(self):
        classifier = ZeroshotClassifier(
            client=mock_zero_shot_client,
        )
        self.assertEqual(classifier.client, mock_zero_shot_client)

    def test_predict_non_other_classification(self):

        mock_response = {"classification": "test_classification"}
        classifier = ZeroshotClassifier(chatbot_goal="test", client=lambda goal: mock_zero_shot_client(goal, response=mock_response))
        classification = classifier.predict("test", self.flow_list)
        self.assertEqual(classification, "test_classification")
