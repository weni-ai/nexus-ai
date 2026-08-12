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
        GUARDRAILS_BEDROCK_TOPIC_TIER="STANDARD",
        GUARDRAILS_BEDROCK_GUARDRAIL_PROFILE_IDENTIFIER="us.guardrail.v1:0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    def test_build_create_guardrail_payload_omits_empty_baselines(self):
        payload = BedrockGuardrailPoolService.build_create_guardrail_payload(
            combination_key="politics",
            blocked_slugs=["politics"],
        )
        self.assertEqual(payload["blockedInputMessaging"], "Blocked.")
        self.assertIn("topicPolicyConfig", payload)
        self.assertEqual(payload["topicPolicyConfig"]["tierConfig"]["tierName"], "STANDARD")
        self.assertEqual(
            payload["crossRegionConfig"]["guardrailProfileIdentifier"],
            "us.guardrail.v1:0",
        )
        self.assertNotIn("contentPolicyConfig", payload)
        self.assertNotIn("sensitiveInformationPolicyConfig", payload)

    @override_settings(
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={"en-us": "Blocked.", "pt-br": "Blocked.", "es": "Blocked."},
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[{"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"}],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[{"type": "EMAIL", "action": "ANONYMIZE"}],
        GUARDRAILS_BEDROCK_TOPIC_TIER="CLASSIC",
        GUARDRAILS_BEDROCK_GUARDRAIL_PROFILE_IDENTIFIER="",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    def test_build_create_guardrail_payload_includes_configured_baselines(self):
        payload = BedrockGuardrailPoolService.build_create_guardrail_payload(
            combination_key="politics",
            blocked_slugs=["politics"],
        )
        self.assertEqual(payload["contentPolicyConfig"]["filtersConfig"][0]["type"], "HATE")
        self.assertEqual(payload["sensitiveInformationPolicyConfig"]["piiEntitiesConfig"][0]["type"], "EMAIL")
        self.assertEqual(payload["topicPolicyConfig"]["tierConfig"]["tierName"], "CLASSIC")
        self.assertNotIn("crossRegionConfig", payload)

    @override_settings(
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={"en-us": "Blocked.", "pt-br": "Blocked.", "es": "Blocked."},
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[],
        GUARDRAILS_BEDROCK_TOPIC_TIER="STANDARD",
        GUARDRAILS_BEDROCK_GUARDRAIL_PROFILE_IDENTIFIER="",
        AWS_BEDROCK_REGION_NAME="eu-central-1",
    )
    def test_build_create_guardrail_payload_derives_eu_profile_for_standard(self):
        payload = BedrockGuardrailPoolService.build_create_guardrail_payload(
            combination_key="politics",
            blocked_slugs=["politics"],
        )
        self.assertEqual(
            payload["crossRegionConfig"]["guardrailProfileIdentifier"],
            "eu.guardrail.v1:0",
        )

    @override_settings(
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={"en-us": "Blocked.", "pt-br": "Blocked.", "es": "Blocked."},
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[],
    )
    def test_build_create_guardrail_payload_accepts_name_suffix(self):
        payload = BedrockGuardrailPoolService.build_create_guardrail_payload(
            combination_key="politics",
            blocked_slugs=["politics"],
            name_suffix="abc12345",
        )
        self.assertIn("abc12345", payload["name"])

    @override_settings(
        GUARDRAILS_BEDROCK_CONTENT_FILTERS=[],
        GUARDRAILS_BEDROCK_PII_ENTITIES=[],
    )
    def test_recreate_pool_creates_repoints_and_deletes_old(self):
        pool = BedrockGuardrailPool.objects.create(
            combination_key="politics",
            category_slugs=["politics"],
            bedrock_guardrail_identifier="gr-old",
            bedrock_guardrail_version="DRAFT",
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
        client.create_guardrail.return_value = {"guardrailId": "gr-new", "version": "DRAFT"}
        client.delete_guardrail.return_value = {}

        with patch.object(
            BedrockGuardrailPoolService,
            "_invalidate_guardrails_cache_for_pool",
        ) as mock_invalidate:
            version = BedrockGuardrailPoolService.recreate_pool(pool, client=client)

        self.assertEqual(version, "DRAFT")
        client.create_guardrail.assert_called_once()
        create_kwargs = client.create_guardrail.call_args.kwargs
        self.assertNotIn("contentPolicyConfig", create_kwargs)
        self.assertNotIn("sensitiveInformationPolicyConfig", create_kwargs)
        client.delete_guardrail.assert_called_once_with(guardrailIdentifier="gr-old")
        mock_invalidate.assert_called_once()

        pool.refresh_from_db()
        self.assertEqual(pool.bedrock_guardrail_identifier, "gr-new")
        self.assertEqual(pool.bedrock_guardrail_version, "DRAFT")
        config = ProjectGuardrailsConfig.objects.get(project=project)
        self.assertEqual(config.bedrock_guardrail_identifier, "gr-new")
        self.assertEqual(config.bedrock_guardrail_version, "DRAFT")
