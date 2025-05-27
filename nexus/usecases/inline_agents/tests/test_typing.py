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
        # Mock authentication response
        auth_response = MagicMock()
        auth_response.json.return_value = {"access_token": "fake-token"}
        mock_post.side_effect = [auth_response, MagicMock()]

        # Execute the method we want to test
        self.typing_usecase.send_typing_message(
            contact_urn=self.contact_urn,
            msg_external_id=self.msg_external_id
        )

        # Verify if requests.post was called twice
        self.assertEqual(mock_post.call_count, 2)

        # Get arguments from the second call (the main call)
        args, kwargs = mock_post.call_args_list[1]

        # Verify the URL
        self.assertEqual(args[0], f"{settings.FLOWS_REST_ENDPOINT}/api/v2/whatsapp_broadcasts.json")

        # Verify the request body
        expected_body = {
            "urns": [self.contact_urn],
            "msg": {
                "msg_external_id": self.msg_external_id,
                "action_type": "msg/typing_indicator"
            }
        }
        self.assertEqual(kwargs['json'], expected_body)

        # Verify if headers were passed correctly
        self.assertIn('headers', kwargs)
        self.assertIn('Authorization', kwargs['headers'])
        self.assertTrue(kwargs['headers']['Authorization'].startswith('Bearer '))
