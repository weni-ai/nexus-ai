import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.clients.flows.http.send_message import SendMessageHTTPClient, WhatsAppBroadcastHTTPClient
from router.dispatcher import dispatch
from router.entities.mailroom import message_factory


class DispatchIgCommentBroadcastTestCase(SimpleTestCase):
    def test_passes_ig_comment_fields_to_broadcast(self):
        broadcast = MagicMock()
        message = message_factory(
            project_uuid="proj",
            text="overwrite message: ig_comment",
            contact_urn="instagram:5467890213",
            metadata={
                "overwrite_message": {
                    "ig_comment": {
                        "id": "30065221",
                        "media": {"id": "180615383", "caption": "Summer sale post"},
                    }
                }
            },
        )

        dispatch(
            message=message,
            user_email="user@example.com",
            llm_response="Obrigado pelo comentário!",
            direct_message=broadcast,
        )

        kwargs = broadcast.send_direct_message.call_args.kwargs
        self.assertEqual(kwargs["ig_comment_id"], "30065221")
        self.assertEqual(kwargs["ig_response_type"], "dm_comment")

    def test_omits_ig_fields_on_non_instagram_turns(self):
        broadcast = MagicMock()
        message = message_factory(
            project_uuid="proj",
            text="hello",
            contact_urn="whatsapp:5511999999999",
            metadata={},
        )

        dispatch(
            message=message,
            user_email="user@example.com",
            llm_response="hi",
            direct_message=broadcast,
        )

        kwargs = broadcast.send_direct_message.call_args.kwargs
        self.assertNotIn("ig_comment_id", kwargs)
        self.assertNotIn("ig_response_type", kwargs)


class SendMessageHTTPClientIgCommentTestCase(SimpleTestCase):
    @patch("router.clients.flows.http.send_message.requests.post")
    def test_mr_msg_send_includes_ig_comment_fields(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        client = SendMessageHTTPClient("http://flows.example", "token")

        client.send_direct_message(
            "Obrigado pelo comentário!",
            ["instagram:5467890213"],
            "project-uuid",
            "user@example.com",
            full_chunks=[],
            ig_comment_id="30065221",
            ig_response_type="dm_comment",
        )

        body = json.loads(mock_post.call_args.kwargs["data"])
        self.assertEqual(body["text"], "Obrigado pelo comentário!")
        self.assertEqual(body["ig_comment_id"], "30065221")
        self.assertEqual(body["ig_response_type"], "dm_comment")
        self.assertEqual(mock_post.call_args.args[0], "http://flows.example/mr/msg/send")

    @patch("router.clients.flows.http.send_message.requests.post")
    def test_mr_msg_send_omits_ig_fields_without_comment(self, mock_post):
        mock_post.return_value.raise_for_status = MagicMock()
        client = SendMessageHTTPClient("http://flows.example", "token")

        client.send_direct_message(
            "hello",
            ["whatsapp:5511999999999"],
            "project-uuid",
            "user@example.com",
            full_chunks=[],
        )

        body = json.loads(mock_post.call_args.kwargs["data"])
        self.assertEqual(body["text"], "hello")
        self.assertNotIn("ig_comment_id", body)
        self.assertNotIn("ig_response_type", body)

    @patch("router.clients.flows.http.send_message.FlowsRESTClient")
    def test_grpc_stream_msg_includes_ig_comment_fields(self, mock_rest):
        mock_rest.return_value.whatsapp_broadcast.return_value.raise_for_status = MagicMock()
        client = SendMessageHTTPClient("http://flows.example", "token", use_grpc=True)

        client.send_direct_message(
            "Obrigado pelo comentário!",
            ["instagram:5467890213"],
            "project-uuid",
            "user@example.com",
            full_chunks=[],
            ig_comment_id="30065221",
            ig_response_type="dm_comment",
        )

        sent_msg = mock_rest.return_value.whatsapp_broadcast.call_args.args[1]
        self.assertEqual(
            sent_msg["msg"],
            {
                "text": "Obrigado pelo comentário!",
                "ig_comment_id": "30065221",
                "ig_response_type": "dm_comment",
            },
        )


class WhatsAppBroadcastHTTPClientIgCommentTestCase(SimpleTestCase):
    @patch("router.clients.flows.http.send_message.FlowsRESTClient")
    def test_whatsapp_broadcast_msg_includes_ig_comment_fields(self, mock_rest):
        mock_rest.return_value.whatsapp_broadcast.return_value.raise_for_status = MagicMock()
        client = WhatsAppBroadcastHTTPClient("http://flows.example", "token")

        client.send_direct_message(
            "Obrigado pelo comentário!",
            ["instagram:5467890213"],
            "project-uuid",
            "user@example.com",
            full_chunks=[],
            backend="OpenAIBackend",
            ig_comment_id="30065221",
            ig_response_type="dm_comment",
        )

        sent_msg = mock_rest.return_value.whatsapp_broadcast.call_args.args[1]
        self.assertEqual(sent_msg["msg"]["text"], "Obrigado pelo comentário!")
        self.assertEqual(sent_msg["msg"]["ig_comment_id"], "30065221")
        self.assertEqual(sent_msg["msg"]["ig_response_type"], "dm_comment")
        self.assertNotIn("media", sent_msg["msg"])

    @patch("router.clients.flows.http.send_message.FlowsRESTClient")
    def test_whatsapp_broadcast_omits_ig_fields_without_comment(self, mock_rest):
        mock_rest.return_value.whatsapp_broadcast.return_value.raise_for_status = MagicMock()
        client = WhatsAppBroadcastHTTPClient("http://flows.example", "token")

        client.send_direct_message(
            "hello",
            ["whatsapp:5511999999999"],
            "project-uuid",
            "user@example.com",
            full_chunks=[],
            backend="OpenAIBackend",
        )

        sent_msg = mock_rest.return_value.whatsapp_broadcast.call_args.args[1]
        self.assertEqual(sent_msg, {"msg": {"text": "hello"}})
