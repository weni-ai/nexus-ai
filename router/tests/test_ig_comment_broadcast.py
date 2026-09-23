import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from router.clients.flows.http.send_message import (
    InstagramCommentBroadcastHTTPClient,
    SendMessageHTTPClient,
    WhatsAppBroadcastHTTPClient,
)
from router.dispatcher import dispatch
from router.entities.mailroom import message_factory
from router.tasks.actions_client import get_action_clients


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
        self.assertNotIn("ig_response_type", kwargs)

    def test_repasses_ig_response_type_when_mailroom_sends_it(self):
        broadcast = MagicMock()
        message = message_factory(
            project_uuid="proj",
            text="overwrite message: ig_comment",
            contact_urn="instagram:5467890213",
            metadata={
                "overwrite_message": {
                    "ig_comment": {"id": "30065221"},
                    "ig_response_type": "dm_comment",
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
    def test_mr_msg_send_ignores_ig_comment_fields(self, mock_post):
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
        self.assertNotIn("ig_comment_id", body)
        self.assertNotIn("ig_response_type", body)
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


class InstagramCommentBroadcastHTTPClientTestCase(SimpleTestCase):
    @patch("router.clients.flows.http.send_message.FlowsRESTClient")
    def test_wraps_json_looking_plain_text_without_component_parsing(self, mock_rest):
        mock_rest.return_value.whatsapp_broadcast.return_value.raise_for_status = MagicMock()
        client = InstagramCommentBroadcastHTTPClient("http://flows.example", "token")
        response_text = '{"status": "available"}'

        client.send_direct_message(
            response_text,
            ["instagram:5467890213"],
            "project-uuid",
            "user@example.com",
            full_chunks=[],
            backend="OpenAIBackend",
            ig_comment_id="30065221",
            ig_response_type="dm_comment",
        )

        sent_msg = mock_rest.return_value.whatsapp_broadcast.call_args.args[1]
        self.assertEqual(
            sent_msg,
            {
                "msg": {
                    "text": response_text,
                    "ig_comment_id": "30065221",
                    "ig_response_type": "dm_comment",
                }
            },
        )
        self.assertEqual(mock_rest.return_value.whatsapp_broadcast.call_args.kwargs["timeout"], 30)

    @patch("router.clients.flows.http.send_message.FlowsRESTClient")
    def test_flattens_component_messages_into_one_comment_reply(self, mock_rest):
        mock_rest.return_value.whatsapp_broadcast.return_value.raise_for_status = MagicMock()
        client = InstagramCommentBroadcastHTTPClient("http://flows.example", "token")
        component_response = json.dumps(
            [
                {"msg": {"text": "Primeira parte", "quick_replies": ["Comprar"]}},
                {"msg": {"text": "Segunda parte"}},
            ]
        )

        client.send_direct_message(
            component_response,
            ["instagram:5467890213"],
            "project-uuid",
            "user@example.com",
            full_chunks=[],
            backend="OpenAIBackend",
            ig_comment_id="30065221",
        )

        sent_msg = mock_rest.return_value.whatsapp_broadcast.call_args.args[1]
        self.assertEqual(
            sent_msg,
            {
                "msg": {
                    "text": "Primeira parte\n\nSegunda parte",
                    "ig_comment_id": "30065221",
                }
            },
        )
        mock_rest.return_value.whatsapp_broadcast.assert_called_once()


@override_settings(AGENT_USE_COMPONENTS=False, GRPC_ENABLED_PROJECTS=["project-uuid"])
class InstagramCommentActionClientTestCase(SimpleTestCase):
    def test_forces_plain_text_broadcast_for_comment_without_components(self):
        client, _ = get_action_clients(
            multi_agents=True,
            project_use_components=False,
            project_uuid="project-uuid",
            stream_support=True,
            force_instagram_comment_broadcast=True,
        )

        self.assertIsInstance(client, InstagramCommentBroadcastHTTPClient)

    def test_keeps_send_message_client_for_regular_instagram_dm(self):
        client, _ = get_action_clients(
            multi_agents=True,
            project_use_components=False,
            project_uuid="project-uuid",
            stream_support=False,
            force_instagram_comment_broadcast=False,
        )

        self.assertIsInstance(client, SendMessageHTTPClient)

    def test_forces_single_comment_client_when_components_are_enabled(self):
        client, _ = get_action_clients(
            multi_agents=True,
            project_use_components=True,
            project_uuid="project-uuid",
            stream_support=False,
            force_instagram_comment_broadcast=True,
        )

        self.assertIs(type(client), InstagramCommentBroadcastHTTPClient)
