import re
from django.test import TestCase

from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers.chatgpt_function import ChatGPTFunctionClassifier
from router.classifiers.mocks import (
    MockFunction,
    MockToolCall,
    MockMessage,
    MockChoice,
    MockResponse,
    MockOpenAIClient,
    MockZeroShotClient
)

from nexus.usecases.actions.tests.flow_factory import FlowFactory
from router.entities.flow import FlowDTO


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
        classifier = ZeroshotClassifier(chatbot_goal="test", client=MockZeroShotClient)
        classification = classifier.predict("test", self.flow_list)
        self.assertEqual(classification, "other")

    def test_predict_with_classification(self):
        classifier = ZeroshotClassifier(chatbot_goal="test", client=MockZeroShotClient)
        classification = classifier.predict("test", self.flow_list)
        self.assertEqual(classification, "other")

    def test_zeroshotclassifier(self):
        classifier = ZeroshotClassifier(
            client=MockZeroShotClient,
        )
        self.assertEqual(classifier.client, MockZeroShotClient)

    def test_predict_non_other_classification(self):

        mock_response = {"classification": "test_classification"}
        classifier = ZeroshotClassifier(chatbot_goal="test", client=lambda goal: MockZeroShotClient(goal, response=mock_response))
        classification = classifier.predict("test", self.flow_list)
        self.assertEqual(classification, "test_classification")


class TestChatGPTFunctionClassifier(TestCase):

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

        function_name = re.sub(r'[^a-zA-Z0-9_-]', '_', self.flow_list[0].name)
        function = MockFunction(function_name)
        tool_call = MockToolCall(function)
        message = MockMessage([tool_call])
        choice = MockChoice(message)
        self.mock_response = MockResponse([choice])
        self.mock_client = MockOpenAIClient(response=self.mock_response)
        self.chatgpt_model = "gpt-3.5-turbo"

        self.classifier = ChatGPTFunctionClassifier(
            client=self.mock_client,
            chatgpt_model=self.chatgpt_model,
        )

    def test_predict(self):
        message = "Test message"

        classification = self.classifier.predict(message, self.flow_list)

        expected_name = self.flow_list[0].name
        self.assertEqual(classification, expected_name)

    def test_predict_no_tool_calls(self):
        self.mock_client = MockOpenAIClient(empty_tool_calls=True)
        self.classifier.client = self.mock_client

        message = "Test message"

        classification = self.classifier.predict(message, self.flow_list)

        self.assertEqual(classification, self.classifier.CLASSIFICATION_OTHER)
