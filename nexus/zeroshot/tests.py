from django.test import TestCase
from nexus.zeroshot.client import InvokeModel
from unittest.mock import patch


class TestClient(TestCase):
    def setUp(self) -> None:
        self.zeroshot_data = {
            'context': 'Test',
            'language': 'por',
            'text': 'oi',
            'options': []
        }

    @patch("nexus.zeroshot.client.InvokeModel._invoke_bedrock")
    def test_call_bedrock(self, mock):
        invoke_model = InvokeModel(self.zeroshot_data, model_backend="bedrock")
        invoke_model.invoke()
        self.assertTrue(mock.called)

    @patch("nexus.zeroshot.client.InvokeModel._invoke_runpod")
    def test_call_runpod(self, mock):
        invoke_model = InvokeModel(self.zeroshot_data, model_backend="runpod")
        invoke_model.invoke()
        self.assertTrue(mock.called)

    def test_value_error(self):
        invoke_model = InvokeModel(self.zeroshot_data, model_backend="err")
        with self.assertRaises(ValueError):
            invoke_model.invoke()
