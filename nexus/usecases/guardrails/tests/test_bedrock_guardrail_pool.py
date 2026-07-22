from unittest.mock import MagicMock

from botocore.exceptions import ClientError
from django.test import TestCase, override_settings

from nexus.projects.models import BedrockGuardrailPool
from nexus.usecases.guardrails.bedrock_guardrail_pool import (
    BedrockGuardrailPoolError,
    BedrockGuardrailPoolService,
)


class BedrockGuardrailPoolServiceTestCase(TestCase):
    def test_combination_key_is_sorted_and_stable(self):
        key = BedrockGuardrailPoolService.combination_key(["hate", "politics", "bias"])
        self.assertEqual(key, "bias|hate|politics")
        self.assertEqual(
            key,
            BedrockGuardrailPoolService.combination_key({"politics", "bias", "hate"}),
        )

    def test_blocked_slugs_from_states(self):
        slugs = BedrockGuardrailPoolService.blocked_slugs_from_states(
            {"politics": True, "hate": False, "bias": True},
        )
        self.assertEqual(slugs, ["bias", "politics"])

    def test_build_topics_config_uses_catalog_definitions(self):
        topics = BedrockGuardrailPoolService.build_topics_config(["politics"])
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0]["name"], "politics")
        self.assertEqual(topics[0]["type"], "DENY")
        self.assertIn("Political", topics[0]["definition"])
        self.assertTrue(topics[0]["examples"])

    def test_get_or_create_pool_returns_none_when_all_unblocked(self):
        result = BedrockGuardrailPoolService.get_or_create_pool(
            {"politics": False, "hate": False},
            client=MagicMock(),
        )
        self.assertIsNone(result)
        self.assertEqual(BedrockGuardrailPool.objects.count(), 0)

    def test_get_or_create_pool_creates_once_and_reuses(self):
        client = MagicMock()
        client.create_guardrail.return_value = {
            "guardrailId": "gr-abc",
            "version": "1",
        }
        states = {"politics": True, "hate": False}

        first = BedrockGuardrailPoolService.get_or_create_pool(states, client=client)
        second = BedrockGuardrailPoolService.get_or_create_pool(states, client=client)

        self.assertIsNotNone(first)
        self.assertTrue(first.created)
        self.assertEqual(first.pool.bedrock_guardrail_identifier, "gr-abc")
        self.assertEqual(first.pool.combination_key, "politics")

        self.assertIsNotNone(second)
        self.assertFalse(second.created)
        self.assertEqual(second.pool.id, first.pool.id)
        self.assertEqual(client.create_guardrail.call_count, 1)

    def test_get_or_create_pool_raises_on_bedrock_error(self):
        client = MagicMock()
        client.create_guardrail.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "CreateGuardrail",
        )

        with self.assertRaises(BedrockGuardrailPoolError):
            BedrockGuardrailPoolService.get_or_create_pool({"politics": True}, client=client)

        self.assertEqual(BedrockGuardrailPool.objects.count(), 0)

    @override_settings(
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGE="Blocked.",
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[{"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"}],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[{"type": "EMAIL", "action": "BLOCK"}],
    )
    def test_build_create_guardrail_payload_includes_baseline(self):
        payload = BedrockGuardrailPoolService.build_create_guardrail_payload(
            combination_key="politics",
            blocked_slugs=["politics"],
        )
        self.assertEqual(payload["blockedInputMessaging"], "Blocked.")
        self.assertIn("topicPolicyConfig", payload)
        self.assertEqual(payload["contentPolicyConfig"]["filtersConfig"][0]["type"], "HATE")
        self.assertEqual(payload["sensitiveInformationPolicyConfig"]["piiEntitiesConfig"][0]["type"], "EMAIL")
