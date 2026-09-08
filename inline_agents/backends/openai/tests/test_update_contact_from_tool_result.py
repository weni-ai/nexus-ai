import json
from types import SimpleNamespace

from django.test import SimpleTestCase

from inline_agents.backends.openai.hooks import _update_contact_from_tool_result


class UpdateContactFromToolResultTests(SimpleTestCase):
    def _context_data(self, fields=None):
        return SimpleNamespace(
            contact={
                "urn": "ext:1464882569744@",
                "channel_uuid": "f8281f0f-c2d6-431d-93f5-798a8cbb0920",
                "name": "1464882569744@",
                "fields": fields if fields is not None else {"email": None},
            }
        )

    def test_merges_email_when_fields_email_was_none(self):
        context_data = self._context_data(fields={"email": None})
        result = {
            "result": {"is_final_output": True},
            "messages_sent": [],
            "contacts_get": [None],
            "contacts_updated": [{"fields": {"email": "user@example.com"}}],
        }
        _update_contact_from_tool_result(context_data, result)
        self.assertEqual(context_data.contact["fields"]["email"], "user@example.com")

    def test_ignores_null_entries_in_contacts_updated(self):
        context_data = self._context_data(fields={"email": None})
        result = {
            "contacts_updated": [None, {"fields": {"email": "user@example.com"}}, None],
        }
        _update_contact_from_tool_result(context_data, result)
        self.assertEqual(context_data.contact["fields"]["email"], "user@example.com")

    def test_noop_without_contacts_updated(self):
        context_data = self._context_data(fields={"email": None})
        result = {"result": {"is_final_output": True}, "messages_sent": []}
        _update_contact_from_tool_result(context_data, result)
        self.assertEqual(context_data.contact["fields"], {"email": None})

    def test_accepts_json_string_result(self):
        context_data = self._context_data(fields={"email": None})
        result = json.dumps(
            {
                "contacts_updated": [{"fields": {"email": "user@example.com"}}],
            }
        )
        _update_contact_from_tool_result(context_data, result)
        self.assertEqual(context_data.contact["fields"]["email"], "user@example.com")

    def test_preserves_fields_keys_not_in_update(self):
        context_data = self._context_data(fields={"email": None, "name": "Alice"})
        result = {"contacts_updated": [{"fields": {"email": "user@example.com"}}]}
        _update_contact_from_tool_result(context_data, result)
        self.assertEqual(
            context_data.contact["fields"],
            {"email": "user@example.com", "name": "Alice"},
        )
