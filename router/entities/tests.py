import importlib.util
import json
import re
from pathlib import Path
from unittest import TestCase

_MAILROOM_PATH = Path(__file__).resolve().parent / "mailroom.py"
_SPEC = importlib.util.spec_from_file_location("router.entities.mailroom", str(_MAILROOM_PATH))
_MAILROOM = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MAILROOM)
message_factory = _MAILROOM.message_factory


class MailroomMessageTest(TestCase):
    def test_contact_fields_serialization(self):
        message = message_factory(
            project_uuid="123",
            text="Hello",
            contact_urn="123",
            contact_fields={
                "cpf": {"value": "123456", "type": "text"},
                "age": {"value": 26, "type": "number"},
            },
        )

        expected_result = json.dumps({"cpf": "123456", "age": 26})
        self.assertEqual(message.contact_fields_as_json, expected_result)

    def test_contact_fields_with_none_value(self):
        message = message_factory(
            project_uuid="123",
            text="Hello",
            contact_urn="123",
            contact_fields={
                "cpf": None,
                "age": {"value": 26, "type": "number"},
            },
        )

        expected_result = json.dumps({"cpf": None, "age": 26})
        self.assertEqual(message.contact_fields_as_json, expected_result)

    def test_empty_contact_fields(self):
        message = message_factory(
            project_uuid="123",
            text="Hello",
            contact_urn="123",
            contact_fields={},
        )

        expected_result = json.dumps({})
        self.assertEqual(message.contact_fields_as_json, expected_result)

    def test_missing_contact_fields(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123")

        expected_result = json.dumps({})
        self.assertEqual(message.contact_fields_as_json, expected_result)

    def test_metadata_serialization_with_values(self):
        message = message_factory(
            project_uuid="123",
            text="Hello",
            contact_urn="123",
            metadata={"123": "12"},
        )

        self.assertIsNotNone(message.metadata)
        self.assertEqual(message.metadata, {"123": "12"})

    def test_metadata_serialization_with_none(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123", metadata={})

        self.assertEqual(message.metadata, {})

    def test_metadata_serialization_without_metadata(self):
        message = message_factory(project_uuid="123", text="Hello", contact_urn="123")

        self.assertEqual(message.metadata, {})

    def test_sanitize_webchat_urn_with_at_after_number(self):
        contact_urn = "ext:1234567890@webchat.ai"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        expected = "ext:1234567890"
        self.assertEqual(message.sanitized_urn, expected)

    def test_sanitize_webchat_urn_with_multiple_ats(self):
        contact_urn = "ext:1234567890@webchat.ai@another.domain"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        expected = "ext:1234567890"
        self.assertEqual(message.sanitized_urn, expected)

    def test_sanitize_webchat_urn_no_at_after_number(self):
        contact_urn = "ext:1234567890"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        self.assertEqual(message.sanitized_urn, contact_urn)

    def test_sanitize_webchat_urn_at_before_number(self):
        contact_urn = "ext@domain:1234567890"
        expected = "ext_64domain:1234567890"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        self.assertEqual(message.sanitized_urn, expected)

    def test_sanitize_webchat_urn_no_colon_number_pattern(self):
        contact_urn = "ext@domain.com"
        expected = "ext_64domain.com"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        self.assertEqual(message.sanitized_urn, expected)

    def test_sanitize_webchat_urn_complex_path(self):
        contact_urn = "project-891f3bfc-76c7-4fab-9cb0-42534b59d3cc-session-ext:212034573131@webchat.ai.test"
        expected = "project-891f3bfc-76c7-4fab-9cb0-42534b59d3cc-session-ext:212034573131"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        self.assertEqual(message.sanitized_urn, expected)

    def test_sanitize_webchat_urn_special_characters(self):
        contact_urn = "ext:1234567890@domain.com"
        expected = "ext:1234567890"
        message = message_factory(project_uuid="123", text="Hello", contact_urn=contact_urn)
        self.assertEqual(message.sanitized_urn, expected)

    def test_regex_pattern_directly(self):
        pattern = r"(:[0-9]+)@.*"
        test_cases = [
            # Cases that should be removed
            ("ext:1234567890@domain.com", "ext:1234567890"),
            (
                "project-891f3bfc-76c7-4fab-9cb0-42534b59d3cc-session-ext:212034573131@cartaopresente.alobebe.com.br",
                "project-891f3bfc-76c7-4fab-9cb0-42534b59d3cc-session-ext:212034573131",
            ),
            ("ext:123@domain@another.com", "ext:123"),
            # Cases that should not be modified by the regex pattern the @ will be sanitized after
            ("ext@domain:1234567890", "ext@domain:1234567890"),
            ("ext:1234567890", "ext:1234567890"),
            ("ext@domain.com", "ext@domain.com"),
            ("ext:abc@domain.com", "ext:abc@domain.com"),
            ("", ""),
        ]

        for input_urn, expected in test_cases:
            result = re.sub(pattern, r"\1", input_urn) if re.search(pattern, input_urn) else input_urn
            assert result == expected, f"Input: {input_urn}\nExpected: {expected}\nGot: {result}"

    def test_edge_cases_with_message_factory(self):
        edge_cases = [
            ("ext:123@", "ext:123"),
            ("ext:123@domain", "ext:123"),
            ("ext:123@domain.com/path", "ext:123"),
            ("ext:123@domain.com:8080", "ext:123"),
            ("ext:123@domain.com#fragment", "ext:123"),
            ("ext:123@domain.com?param=value", "ext:123"),
            ("ext:123@domain.com", "ext:123"),
            ("ext:123@domain.com", "ext:123"),
            ("ext:0@domain.com", "ext:0"),
            ("ext:999999999999999@domain.com", "ext:999999999999999"),
            ("ext:123456789@domain.com", "ext:123456789"),
        ]

        for input_urn, expected in edge_cases:
            message = message_factory(project_uuid="123", text="Hello", contact_urn=input_urn)
            result = message.sanitized_urn
            assert result == expected, f"Input: {input_urn}\nExpected: {expected}\nGot: {result}"

    def test_contact_fields_non_text_types(self):
        message = message_factory(
            project_uuid="123",
            text="Hello",
            contact_urn="123",
            contact_fields={"flag": {"value": True, "type": "boolean"}, "score": {"value": 9.5, "type": "float"}},
        )
        assert json.loads(message.contact_fields_as_json) == {"flag": True, "score": 9.5}
