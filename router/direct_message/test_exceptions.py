from unittest import TestCase
from unittest.mock import MagicMock, patch

from router.direct_message.exceptions import UnableToSendMessage, raise_unable_to_send_from_response


class RaiseUnableToSendFromResponseTests(TestCase):
    @patch("router.direct_message.exceptions.sentry_sdk")
    def test_attaches_response_body_to_exception_and_sentry(self, mock_sentry):
        response = MagicMock()
        response.status_code = 400
        response.url = "https://flows.weni.ai/api/v2/internals/whatsapp_broadcasts"
        response.text = (
            '{"non_field_errors":["Sorry, your workspace is currently suspended. '
            'To re-enable starting flows and sending messages, please contact support."]}'
        )
        error = Exception("400 Client Error: Bad Request for url: https://flows.weni.ai/api/v2/internals/whatsapp_broadcasts")

        with self.assertRaises(UnableToSendMessage) as ctx:
            raise_unable_to_send_from_response(
                error,
                response,
                project_uuid="cfe42735-935f-4ef6-9af1-3c6e24e0d5aa",
                urns=["ext:roger.alexandre@vtex.com"],
            )

        message = str(ctx.exception)
        self.assertIn("400 Client Error", message)
        self.assertIn("workspace is currently suspended", message)
        mock_sentry.set_context.assert_called_once()
        context_name, payload = mock_sentry.set_context.call_args[0]
        self.assertEqual(context_name, "flows_response")
        self.assertEqual(payload["status_code"], 400)
        self.assertEqual(payload["project_uuid"], "cfe42735-935f-4ef6-9af1-3c6e24e0d5aa")
        self.assertIn("workspace is currently suspended", payload["response_body"])

    @patch("router.direct_message.exceptions.sentry_sdk")
    def test_truncates_long_response_body(self, mock_sentry):
        response = MagicMock()
        response.status_code = 400
        response.url = "https://flows.weni.ai/api/v2/internals/whatsapp_broadcasts"
        response.text = "x" * 5000
        error = Exception("400 Client Error")

        with self.assertRaises(UnableToSendMessage) as ctx:
            raise_unable_to_send_from_response(error, response)

        self.assertEqual(len(ctx.exception.args[0].split("response_body=", 1)[1]), 2000)
        payload = mock_sentry.set_context.call_args[0][1]
        self.assertEqual(len(payload["response_body"]), 2000)
