from unittest import mock

from django.test import override_settings
from rest_framework import status
from rest_framework.test import force_authenticate

from nexus.projects.api.tests.test_conversations_proxy_permissions import _PermissionTestBase
from nexus.projects.api.views import OpenSupportTicketView
from nexus.projects.services.improvement_support_email import (
    build_improvement_support_email_body,
    send_improvement_support_ticket,
)

_SEND_TICKET = "nexus.projects.api.views.send_improvement_support_ticket"

VALID_PAYLOAD = {
    "improvement_item": {
        "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "text": "Cancellation denied",
        "type": "wrong_behavior_due_to_instructions",
        "description": "The agent refused cancellation even though the policy allows it within 7 days.",
        "suggested_change": "Edit instruction 15684.",
        "affected_instructions": [
            {
                "instruction_id": 15684,
                "change_type": "fix",
                "was_changed": False,
            }
        ],
    },
    "affected_conversations": [
        {
            "uuid": "f9e8d7c6-b5a4-3210-fedc-ba9876543210",
            "contact_urn": "whatsapp:+5511999999999",
            "contact_name": "Maria",
            "started_at": "2026-02-05T12:00:00Z",
        },
        {
            "uuid": "c3d4e5f6-a7b8-9012-cdef-345678901234",
            "contact_urn": "whatsapp:+5511888888888",
            "contact_name": "João",
            "started_at": "2026-02-05T14:30:00Z",
        },
    ],
    "project_uuid": None,
    "user_email": "agent@example.com",
}


def _payload_for_project(project_uuid: str) -> dict:
    payload = VALID_PAYLOAD.copy()
    payload["project_uuid"] = project_uuid
    payload["improvement_item"] = VALID_PAYLOAD["improvement_item"].copy()
    payload["affected_conversations"] = [item.copy() for item in VALID_PAYLOAD["affected_conversations"]]
    return payload


class TestOpenSupportTicketView(_PermissionTestBase):
    def setUp(self):
        super().setUp()
        self.view = OpenSupportTicketView.as_view()
        self.url = f"/api/{self.project_uuid}/improvements/open-support-ticket/"

    @mock.patch(_SEND_TICKET, return_value=1)
    def test_project_permission_sends_ticket(self, mock_send_ticket):
        request = self.factory.post(self.url, _payload_for_project(self.project_uuid), format="json")
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "sent")
        mock_send_ticket.assert_called_once()
        call_kwargs = mock_send_ticket.call_args.kwargs
        self.assertEqual(call_kwargs["project_uuid"], self.project_uuid)
        self.assertEqual(call_kwargs["user_email"], "agent@example.com")
        self.assertEqual(call_kwargs["improvement_item"]["text"], "Cancellation denied")
        self.assertEqual(len(call_kwargs["affected_conversations"]), 2)

    @mock.patch(_SEND_TICKET, return_value=1)
    def test_internal_permission_sends_ticket(self, mock_send_ticket):
        request = self.factory.post(self.url, _payload_for_project(self.project_uuid), format="json")
        force_authenticate(request, user=self.internal_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_send_ticket.assert_called_once()

    def test_no_permission_returns_403(self):
        request = self.factory.post(self.url, _payload_for_project(self.project_uuid), format="json")
        force_authenticate(request, user=self.unauthorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch(_SEND_TICKET, return_value=1)
    def test_project_uuid_mismatch_returns_400(self, mock_send_ticket):
        payload = _payload_for_project("017cd5df-cfc8-4d5c-b659-347fe7a4bee9")
        request = self.factory.post(self.url, payload, format="json")
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_send_ticket.assert_not_called()

    @override_settings(SEND_EMAILS=False)
    @mock.patch("nexus.projects.services.improvement_support_email.EmailMessage")
    def test_send_emails_false_skips_email(self, mock_email_message):
        sent = send_improvement_support_ticket(
            project_uuid=self.project_uuid,
            improvement_item=_payload_for_project(self.project_uuid)["improvement_item"],
            affected_conversations=_payload_for_project(self.project_uuid)["affected_conversations"],
            user_email="agent@example.com",
        )

        self.assertEqual(sent, 0)
        mock_email_message.assert_not_called()

    @override_settings(SEND_EMAILS=True, VTEX_SUPPORT_EMAIL="")
    def test_missing_support_email_returns_503(self):
        request = self.factory.post(self.url, _payload_for_project(self.project_uuid), format="json")
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @override_settings(
        DEBUG=False,
        SEND_EMAILS=True,
        VTEX_SUPPORT_EMAIL="support@vtex.com",
        DEFAULT_FROM_EMAIL="no-reply@weni.ai",
    )
    @mock.patch("nexus.projects.services.improvement_support_email.EmailMessage")
    def test_email_message_content(self, mock_email_message):
        mock_instance = mock.Mock()
        mock_instance.send.return_value = 1
        mock_email_message.return_value = mock_instance

        payload = _payload_for_project(self.project_uuid)
        send_improvement_support_ticket(
            project_uuid=self.project_uuid,
            improvement_item=payload["improvement_item"],
            affected_conversations=payload["affected_conversations"],
            user_email="agent@example.com",
        )

        mock_email_message.assert_called_once_with(
            subject=f"Improvement Item - {self.project_uuid}",
            body=build_improvement_support_email_body(
                project_uuid=self.project_uuid,
                improvement_item=payload["improvement_item"],
                affected_conversations=payload["affected_conversations"],
                user_email="agent@example.com",
            ),
            from_email="no-reply@weni.ai",
            to=["support@vtex.com"],
            reply_to=["agent@example.com"],
            connection=None,
        )
        mock_instance.send.assert_called_once_with()

    @override_settings(DEBUG=True, SEND_EMAILS=True, VTEX_SUPPORT_EMAIL="support@vtex.com")
    @mock.patch("nexus.projects.services.improvement_support_email.get_connection")
    @mock.patch("nexus.projects.services.improvement_support_email.EmailMessage")
    def test_debug_uses_console_email_backend(self, mock_email_message, mock_get_connection):
        mock_instance = mock.Mock()
        mock_instance.send.return_value = 1
        mock_email_message.return_value = mock_instance
        mock_get_connection.return_value = mock.Mock()

        payload = _payload_for_project(self.project_uuid)
        send_improvement_support_ticket(
            project_uuid=self.project_uuid,
            improvement_item=payload["improvement_item"],
            affected_conversations=payload["affected_conversations"],
            user_email="agent@example.com",
        )

        mock_get_connection.assert_called_once_with(
            backend="django.core.mail.backends.console.EmailBackend"
        )
        self.assertEqual(mock_email_message.call_args.kwargs["connection"], mock_get_connection.return_value)
        mock_instance.send.assert_called_once_with()

    def test_email_body_contains_signature_and_payload_fields(self):
        payload = _payload_for_project(self.project_uuid)
        body = build_improvement_support_email_body(
            project_uuid=self.project_uuid,
            improvement_item=payload["improvement_item"],
            affected_conversations=payload["affected_conversations"],
            user_email="agent@example.com",
        )

        self.assertIn(f"Project UUID: {self.project_uuid}", body)
        self.assertIn("Submitted by: agent@example.com", body)
        self.assertIn("Cancellation denied", body)
        self.assertIn("wrong_behavior_due_to_instructions", body)
        self.assertIn("instruction_id=15684", body)
        self.assertIn("Maria (whatsapp:+5511999999999)", body)
        self.assertIn("João (whatsapp:+5511888888888)", body)
        self.assertTrue(body.strip().endswith("Submitted by: agent@example.com"))
