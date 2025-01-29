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
