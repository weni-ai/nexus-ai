from unittest import TestCase
from unittest.mock import patch, MagicMock

from django.conf import settings

from nexus.usecases.inline_agents.typing import TypingUsecase


class TestTypingUsecase(TestCase):
    def setUp(self):
        self.typing_usecase = TypingUsecase()
        self.contact_urn = "whatsapp:+5511999999999"
        self.msg_external_id = "test-msg-id"

    @patch('requests.post')
    def test_send_typing_message(self, mock_post):
        # Mock da resposta de autenticação
        auth_response = MagicMock()
        auth_response.json.return_value = {"access_token": "fake-token"}
        mock_post.side_effect = [auth_response, MagicMock()]

        # Executa o método que queremos testar
        self.typing_usecase.send_typing_message(
            contact_urn=self.contact_urn,
            msg_external_id=self.msg_external_id
        )

        # Verifica se o requests.post foi chamado duas vezes
        self.assertEqual(mock_post.call_count, 2)
        
        # Obtém os argumentos da segunda chamada (a chamada principal)
        args, kwargs = mock_post.call_args_list[1]

        # Verifica a URL
        self.assertEqual(args[0], f"{settings.FLOWS_REST_ENDPOINT}/api/v2/whatsapp_broadcasts.json")
        
        # Verifica o corpo da requisição
        expected_body = {
            "urns": [self.contact_urn],
            "msg": {
                "msg_external_id": self.msg_external_id,
                "action_type": "msg/typing_indicator"
            }
        }
        self.assertEqual(kwargs['json'], expected_body)
        
        # Verifica se os headers foram passados corretamente
        self.assertIn('headers', kwargs)
        self.assertIn('Authorization', kwargs['headers'])
        self.assertTrue(kwargs['headers']['Authorization'].startswith('Bearer ')) 