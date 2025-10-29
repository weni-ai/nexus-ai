from unittest.mock import ANY, patch

from django.test import TestCase, override_settings

from nexus.zeroshot.client import InvokeModel
from router.classifiers.chatgpt_function import ChatGPTFunctionClassifier


class TestClient(TestCase):
    def setUp(self) -> None:
        self.zeroshot_data = {"context": "Test", "language": "por", "text": "oi", "options": []}

    @override_settings(DEFAULT_CLASSIFICATION_MODEL="zeroshot")
    @patch("nexus.zeroshot.client.InvokeModel._invoke_bedrock")
    def test_call_bedrock(self, mock):
        invoke_model = InvokeModel(self.zeroshot_data, model_backend="bedrock")
        invoke_model.invoke()
        self.assertTrue(mock.called)

    @override_settings(DEFAULT_CLASSIFICATION_MODEL="zeroshot")
    @patch("nexus.zeroshot.client.InvokeModel._invoke_runpod")
    def test_call_runpod(self, mock):
        invoke_model = InvokeModel(self.zeroshot_data, model_backend="runpod")
        invoke_model.invoke()
        self.assertTrue(mock.called)

    @override_settings(DEFAULT_CLASSIFICATION_MODEL="zeroshot")
    def test_value_error(self):
        invoke_model = InvokeModel(self.zeroshot_data, model_backend="err")
        with self.assertRaises(ValueError):
            invoke_model.invoke()

    @override_settings(DEFAULT_CLASSIFICATION_MODEL="function_calling")
    @patch("nexus.zeroshot.client.InvokeModel._invoke_function_calling")
    def test_call_function_calling(self, mock):
        invoke_model = InvokeModel(self.zeroshot_data, model_backend="zeroshot")
        invoke_model.invoke()
        self.assertTrue(mock.called)


class TestFunctionCalling(TestCase):
    @override_settings(DEFAULT_CLASSIFICATION_MODEL="function_calling")
    def test_invoke_function_calling_calls_correct_methods(self):
        zeroshot_data = {
            "context": "This is the agent goal.",
            "language": "eng",
            "text": "User message to classify.",
            "options": [
                {"class": "Class1", "context": "Context for class 1"},
                {"class": "Class2", "context": "Context for class 2"},
            ],
        }

        with patch.object(ChatGPTFunctionClassifier, "__init__", return_value=None) as mock_init, patch.object(
            ChatGPTFunctionClassifier, "predict", return_value="Class1"
        ) as mock_predict:
            invoke_model = InvokeModel(zeroshot_data)
            response = invoke_model.invoke()

            mock_init.assert_called_with(agent_goal="This is the agent goal.")

            mock_predict.assert_called_with(
                message="User message to classify.",
                flows=ANY,
                language="eng",
            )

            expected_response = {"output": {"other": False, "classification": "Class1"}}
            self.assertEqual(response, expected_response)
