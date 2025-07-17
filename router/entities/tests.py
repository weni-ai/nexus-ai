import json

from django.test import TestCase

from .mailroom import message_factory


class MailroomMessageTest(TestCase):
    def test_contact_fields_serialization(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123", contact_fields={
            "cpf": {
                "value": "123456",
                "type": "text"
            },
            "age": {
                "value": 26,
                "type": "number"
            }
        })

        expected_result = json.dumps({"cpf": "123456", "age": 26})
        self.assertEqual(message.contact_fields_as_json, expected_result)

    def test_contact_fields_with_none_value(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123", contact_fields={
            "cpf": None,
            "age": {
                "value": 26,
                "type": "number"
            }
        })

        expected_result = json.dumps({"cpf": None, "age": 26})
        self.assertEqual(message.contact_fields_as_json, expected_result)

    def test_empty_contact_fields(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123", contact_fields={})

        expected_result = json.dumps({})
        self.assertEqual(message.contact_fields_as_json, expected_result)

    def test_missing_contact_fields(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123")

        expected_result = json.dumps({})
        self.assertEqual(message.contact_fields_as_json, expected_result)

    def test_metadata_serialization_with_values(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123", metadata={"123" : "12"})

        self.assertIsNotNone(message.metadata)
        self.assertEqual(message.metadata, {"123" : "12"})

    def test_metadata_serialization_with_none(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123", metadata=None)

        self.assertEqual(message.metadata, {})

    def test_metadata_serialization_without_metadata(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123")

        self.assertEqual(message.metadata, {})

    def test_sanitize_webchat_urn(self):
        contact_urn = "ext:1234567890@webchat.ai"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        self.assertEqual(message.sanitized_urn, contact_urn.split("@")[0])

    def test_sanitize_webchat_urn_with_multiple_ats(self):
        contact_urn = "ext:1234567890@webchat.ai@webchat.ai"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        self.assertEqual(message.sanitized_urn, contact_urn.split("@")[0])
    
    def test_sanitize_webchat_urn_no_ats(self):
        contact_urn = "ext:1234567890"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        self.assertEqual(message.sanitized_urn, contact_urn)
