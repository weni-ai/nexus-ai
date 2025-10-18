from unittest import TestCase
from unittest.mock import patch, MagicMock
import uuid

from django.conf import settings

from nexus.usecases.inline_agents.typing import TypingUsecase


class TestTypingUsecase(TestCase):
    def setUp(self):
        self.typing_usecase = TypingUsecase()
        self.contact_urn = "whatsapp:+5511999999999"
        self.msg_external_id = "test-msg-id"
        self.project_uuid = str(uuid.uuid4())

    @patch('nexus.usecases.inline_agents.typing.InternalAuthentication')
    def test_send_typing_message(self, mock_auth_class):
        mock_auth_instance = mock_auth_class.return_value

        self.typing_usecase.auth_client = mock_auth_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_auth_instance.make_request_with_retry.return_value = mock_response

        # Execute the method
        self.typing_usecase.send_typing_message(
            contact_urn=self.contact_urn,
            msg_external_id=self.msg_external_id,
            project_uuid=self.project_uuid,
        )

        mock_auth_instance.make_request_with_retry.assert_called_once()

        _, kwargs = mock_auth_instance.make_request_with_retry.call_args
        
        expected_url = f"{settings.FLOWS_REST_ENDPOINT}/api/v2/internals/whatsapp_broadcasts"
        self.assertEqual(kwargs['url'], expected_url)

        expected_body = {
            "urns": [self.contact_urn],
            "project": self.project_uuid,
            "msg": {
                "action_external_id": self.msg_external_id,
                "action_type": "typing_indicator",
            },
        }
        self.assertEqual(kwargs['json'], expected_body)
