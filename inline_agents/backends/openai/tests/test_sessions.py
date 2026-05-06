"""Tests for OpenAI inline Redis session key helpers."""

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from inline_agents.backends.openai.sessions import (
    delete_openai_inline_session_keys_for_contact,
    openai_session_base_id,
)


class DeleteOpenaiInlineSessionKeysTestCase(SimpleTestCase):
    def test_single_redis_delete_batches_all_keys(self):
        client = MagicMock()
        client.delete.return_value = 2
        base = openai_session_base_id("proj-uuid", "sanitized_urn")
        n = delete_openai_inline_session_keys_for_contact(
            client,
            "proj-uuid",
            "sanitized_urn",
            ["agent-a", "agent-b"],
        )
        self.assertEqual(n, 2)
        client.delete.assert_called_once()
        args = client.delete.call_args[0]
        self.assertEqual(set(args), {base, f"{base}:agent-a", f"{base}:agent-b"})

    def test_deduplicates_collaborator_slugs(self):
        client = MagicMock()
        client.delete.return_value = 2
        base = openai_session_base_id("p", "u")
        delete_openai_inline_session_keys_for_contact(client, "p", "u", ["same", "same"])
        args = client.delete.call_args[0]
        self.assertEqual(set(args), {base, f"{base}:same"})
