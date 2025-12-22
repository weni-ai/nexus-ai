import os
import re
from unittest.mock import patch

from django.test import TestCase

from nexus.usecases.actions.tests.flow_factory import FlowFactory
from nexus.usecases.logs.tests.logs_factory import MessageLogFactory
from router.classifiers.chatgpt_function import ChatGPTFunctionClassifier
from router.classifiers.classification import Classification
from router.classifiers.groundedness import Groundedness
from router.classifiers.mocks import (
    MockChoice,
    MockFunction,
    MockMessage,
    MockOpenAIClient,
    MockResponse,
    MockToolCall,
    MockZeroShotClient,
)
from router.classifiers.pre_classification import PreClassification
from router.classifiers.zeroshot import ZeroshotClassifier
from router.entities import Message
from router.entities.flow import FlowDTO
from router.flow_start.interfaces import FlowStart


class TestZeroshotClassifier(TestCase):
    def setUp(self) -> None:
        self.flow_list = []
        batch_flow_build = FlowFactory.build_batch(3)
        for flow in batch_flow_build:
            self.flow_list.append(
                FlowDTO(
                    pk=flow.uuid,
                    uuid=flow.flow_uuid,
                    name=flow.name,
                    prompt=flow.prompt,
                    content_base_uuid=flow.content_base.uuid,
                    fallback=flow.fallback,
                )
            )

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
        classifier = ZeroshotClassifier(
            chatbot_goal="test", client=lambda goal: MockZeroShotClient(goal, response=mock_response)
        )
        classification = classifier.predict("test", self.flow_list)
        self.assertEqual(classification, "test_classification")


class TestChatGPTFunctionClassifier(TestCase):
    def setUp(self) -> None:
        self.flow_list = []
        batch_flow_build = FlowFactory.build_batch(3)
        for flow in batch_flow_build:
            self.flow_list.append(
                FlowDTO(
                    pk=flow.uuid,
                    uuid=flow.flow_uuid,
                    name=flow.name,
                    prompt=flow.prompt,
                    content_base_uuid=flow.content_base.uuid,
                    fallback=flow.fallback,
                )
            )

        function_name = re.sub(r"[^a-zA-Z0-9_-]", "_", self.flow_list[0].name)
        function = MockFunction(function_name)
        tool_call = MockToolCall(function)
        message = MockMessage([tool_call])
        choice = MockChoice(message)
        self.mock_response = MockResponse([choice])
        self.mock_client = MockOpenAIClient(response=self.mock_response)

        self.classifier = ChatGPTFunctionClassifier(client=self.mock_client, agent_goal="Answer user questions")

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


class StubFlowsRepo:
    def project_flows(self, action_type: str, fallback: bool):
        return [
            FlowDTO(
                pk="1",
                uuid="1",
                name="N1",
                prompt="P1",
                content_base_uuid="cb",
                fallback=False,
            )
        ]

    def get_classifier_flow_by_action_type(self, action_type: str):
        return FlowDTO(
            pk="1",
            uuid="1",
            name="Guard",
            prompt="Do guard",
            content_base_uuid="cb",
            fallback=False,
        )


class StubFlowStart(FlowStart):
    def start_flow(self, flow, user, urns, user_message=None, msg_event=None, attachments=None):
        return True


class TestPreClassification(TestCase):
    def test_pre_classification_preview_structure(self):
        repo = StubFlowsRepo()
        msg = Message(project_uuid="p", text="t", contact_urn="u")
        os.environ["USE_SAFEGUARD"] = "false"
        os.environ["USE_PROMPT_GUARD"] = "false"
        pc = PreClassification(
            flows_repository=repo, message=msg, msg_event={}, flow_start=StubFlowStart(), user_email="user"
        )
        out = pc.pre_classification(source="preview")
        assert isinstance(out, dict)


class TestClassification(TestCase):
    def test_non_custom_actions_route_returns_bool(self):
        repo = StubFlowsRepo()
        msg = Message(project_uuid="p", text="t", contact_urn="u")
        cls = Classification(
            flows_repository=repo, message=msg, msg_event={}, flow_start=StubFlowStart(), user_email="user"
        )
        res = cls.non_custom_actions(source="route")
        assert isinstance(res, bool)


class TestGroundednessClassifier(TestCase):
    def setUp(self) -> None:
        self.log = MessageLogFactory()

        class StubMessage:
            def __init__(self, content):
                self.content = content

        class StubChoice:
            def __init__(self, message):
                self.message = message

        class StubResponse:
            def __init__(self, content):
                self.choices = [StubChoice(StubMessage(content))]

        class StubOpenAIClient:
            def __init__(self, api_key):
                self.response_content = ""

            def chat_completions_create(self, messages):
                return StubResponse(self.response_content)

        self.openai_patcher = patch("router.classifiers.groundedness.OpenAIClient", StubOpenAIClient)
        self.openai_patcher.start()

    def tearDown(self) -> None:
        self.openai_patcher.stop()

    def test_extract_score_and_sentences_parses_multiple_items(self):
        groundedness = Groundedness(
            llm_response="resp",
            llm_chunk_used=["chunk"],
            log=self.log,
            system_prompt="system",
            user_prompt="user {{premise}} {{hypothesis}}",
            score_avg_threshold=2,
        )

        content = (
            "Statement Sentence: Alpha, Supporting Evidence: Evid A Score: 3\n"
            "Statement Sentence: Beta Supporting Evidence: Evid B Score: 1 😊"
        )
        result = groundedness.extract_score_and_sentences(content)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["sentence"], "Alpha")
        self.assertEqual(result[0]["evidence"], "Evid A")
        self.assertEqual(result[0]["score"], "3")
        self.assertEqual(result[1]["sentence"], "Beta")
        self.assertEqual(result[1]["evidence"], "Evid B")
        self.assertEqual(result[1]["score"], "1")

    def test_replace_vars_replaces_placeholders(self):
        groundedness = Groundedness(
            llm_response="resp",
            llm_chunk_used=["chunk"],
            log=self.log,
            system_prompt="system",
            user_prompt="user {{premise}} {{hypothesis}}",
            score_avg_threshold=2,
        )
        prompt = "Premise: {{premise}}; Hypothesis: {{hypothesis}}; Num: {{num}}"
        replaced = groundedness.replace_vars(prompt, {"premise": "P", "hypothesis": "H", "num": 42})
        self.assertIn("Premise: P", replaced)
        self.assertIn("Hypothesis: H", replaced)
        self.assertIn("Num: 42", replaced)

    def test_get_prompt_uses_chunks_and_response(self):
        groundedness = Groundedness(
            llm_response="R",
            llm_chunk_used=["A", "B"],
            log=self.log,
            system_prompt="system",
            user_prompt="Premise: {{premise}} Hypothesis: {{hypothesis}}",
            score_avg_threshold=2,
        )
        prompt = groundedness.get_prompt()
        self.assertEqual(prompt, "Premise: AB Hypothesis: R")

    def test_classify_sets_log_fields_and_tag_success(self):
        groundedness = Groundedness(
            llm_response="R",
            llm_chunk_used=["X"],
            log=self.log,
            system_prompt="system",
            user_prompt="Premise: {{premise}} Hypothesis: {{hypothesis}}",
            score_avg_threshold=2,
        )
        groundedness.client.response_content = (
            "Statement Sentence: S1, Supporting Evidence: E1 Score: 3\n"
            "Statement Sentence: S2, Supporting Evidence: E2 Score: 1"
        )
        groundedness.classify()

        self.log.refresh_from_db()
        self.assertEqual(self.log.groundedness_score, 2)
        self.assertEqual(self.log.reflection_data.get("tag"), "success")
        self.assertIn("Statement Sentence: S1", self.log.reflection_data.get("sentence_rankings"))

    def test_classify_sets_failed_when_no_matches(self):
        groundedness = Groundedness(
            llm_response="R",
            llm_chunk_used=["X"],
            log=self.log,
            system_prompt="system",
            user_prompt="Premise: {{premise}} Hypothesis: {{hypothesis}}",
            score_avg_threshold=2,
        )
        groundedness.client.response_content = "No valid content"
        groundedness.classify()

        self.log.refresh_from_db()
        self.assertEqual(self.log.groundedness_score, 0)
        self.assertEqual(self.log.reflection_data.get("tag"), "failed")
