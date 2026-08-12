from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.test import TestCase, override_settings

from nexus.projects.models import BedrockGuardrailPool, ProjectGuardrailsConfig
from nexus.usecases.guardrails.bedrock_guardrail_pool import (
    BedrockGuardrailPoolError,
    BedrockGuardrailPoolService,
)
from nexus.usecases.projects.tests.project_factory import ProjectFactory


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
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={"en-us": "Blocked.", "pt-br": "Blocked.", "es": "Blocked."},
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[],
    )
    def test_build_create_guardrail_payload_omits_empty_baselines(self):
        payload = BedrockGuardrailPoolService.build_create_guardrail_payload(
            combination_key="politics",
            blocked_slugs=["politics"],
        )
        self.assertEqual(payload["blockedInputMessaging"], "Blocked.")
        self.assertIn("topicPolicyConfig", payload)
        self.assertNotIn("contentPolicyConfig", payload)
        self.assertNotIn("sensitiveInformationPolicyConfig", payload)

    @override_settings(
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={"en-us": "Blocked.", "pt-br": "Blocked.", "es": "Blocked."},
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[{"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"}],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[{"type": "EMAIL", "action": "ANONYMIZE"}],
    )
    def test_build_create_guardrail_payload_includes_configured_baselines(self):
        payload = BedrockGuardrailPoolService.build_create_guardrail_payload(
            combination_key="politics",
            blocked_slugs=["politics"],
        )
        self.assertEqual(payload["contentPolicyConfig"]["filtersConfig"][0]["type"], "HATE")
        self.assertEqual(payload["sensitiveInformationPolicyConfig"]["piiEntitiesConfig"][0]["type"], "EMAIL")

    @override_settings(
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[],
    )
    def test_build_update_guardrail_payload_disables_residual_baselines(self):
        payload = BedrockGuardrailPoolService.build_update_guardrail_payload(
            guardrail_identifier="gr-1",
            name="nexus-pool-abc",
            blocked_input_messaging="Blocked.",
            blocked_outputs_messaging="Blocked.",
            blocked_slugs=["politics"],
        )
        self.assertEqual(payload["guardrailIdentifier"], "gr-1")
        self.assertTrue(payload["contentPolicyConfig"]["filtersConfig"])
        self.assertTrue(
            all(item["inputStrength"] == "NONE" for item in payload["contentPolicyConfig"]["filtersConfig"]),
        )
        self.assertEqual(payload["sensitiveInformationPolicyConfig"]["piiEntitiesConfig"], [])
        self.assertEqual(payload["topicPolicyConfig"]["topicsConfig"][0]["name"], "politics")

    @override_settings(
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[],
    )
    def test_sync_pool_policies_updates_publishes_and_propagates(self):
        pool = BedrockGuardrailPool.objects.create(
            combination_key="politics",
            category_slugs=["politics"],
            bedrock_guardrail_identifier="gr-politics",
            bedrock_guardrail_version="1",
        )
        project = ProjectFactory()
        ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states={"politics": True},
            bedrock_guardrail_pool=pool,
            bedrock_guardrail_identifier=pool.bedrock_guardrail_identifier,
            bedrock_guardrail_version=pool.bedrock_guardrail_version,
        )

        client = MagicMock()
        client.get_guardrail.return_value = {
            "name": "nexus-pool-old",
            "description": "old",
            "blockedInputMessaging": "Blocked.",
            "blockedOutputsMessaging": "Blocked.",
        }
        client.update_guardrail.return_value = {"version": "DRAFT"}
        client.create_guardrail_version.return_value = {"version": "2"}

        with patch.object(
            BedrockGuardrailPoolService,
            "_invalidate_guardrails_cache_for_pool",
        ) as mock_invalidate:
            version = BedrockGuardrailPoolService.sync_pool_policies(pool, client=client)

        self.assertEqual(version, "2")
        mock_invalidate.assert_called_once()
        client.get_guardrail.assert_called_once()
        client.update_guardrail.assert_called_once()
        update_kwargs = client.update_guardrail.call_args.kwargs
        self.assertEqual(
            update_kwargs["contentPolicyConfig"]["filtersConfig"][0]["inputStrength"],
            "NONE",
        )
        self.assertEqual(update_kwargs["sensitiveInformationPolicyConfig"]["piiEntitiesConfig"], [])
        client.create_guardrail_version.assert_called_once()
        pool.refresh_from_db()
        self.assertEqual(pool.bedrock_guardrail_version, "2")
        config = ProjectGuardrailsConfig.objects.get(project=project)
        self.assertEqual(config.bedrock_guardrail_version, "2")
