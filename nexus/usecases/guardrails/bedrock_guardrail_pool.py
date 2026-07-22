from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction

from nexus.projects.models import BedrockGuardrailPool

logger = logging.getLogger(__name__)

# Bedrock Denied Topic constraints (API)
_TOPIC_NAME_MAX = 100
_TOPIC_DEFINITION_MAX = 200
_TOPIC_EXAMPLE_MAX = 100
_TOPIC_EXAMPLES_MAX = 5
_GUARDRAIL_NAME_MAX = 50


class BedrockGuardrailPoolError(Exception):
    """Raised when pool resolve/create against Bedrock fails."""


@dataclass(frozen=True)
class ResolvedGuardrailPool:
    pool: BedrockGuardrailPool
    created: bool


class BedrockGuardrailPoolService:
    """Resolve shared Bedrock Guardrail pools by blocked-category combination."""

    @staticmethod
    def combination_key(blocked_slugs: list[str] | set[str]) -> str:
        return "|".join(sorted({slug for slug in blocked_slugs if slug}))

    @classmethod
    def blocked_slugs_from_states(cls, category_states: dict[str, bool] | None) -> list[str]:
        if not category_states:
            return []
        return sorted(slug for slug, blocked in category_states.items() if blocked is True)

    @classmethod
    def catalog_by_slug(cls) -> dict[str, dict]:
        return {entry["slug"]: entry for entry in settings.GUARDRAIL_CATEGORY_CATALOG}

    @classmethod
    def build_topics_config(cls, blocked_slugs: list[str]) -> list[dict]:
        catalog = cls.catalog_by_slug()
        topics: list[dict] = []
        for slug in blocked_slugs:
            entry = catalog.get(slug)
            if not entry:
                continue
            definition = str(entry.get("bedrock_definition") or entry.get("description") or slug)
            examples_raw = entry.get("bedrock_examples") or []
            examples = [
                str(example)[:_TOPIC_EXAMPLE_MAX]
                for example in examples_raw[:_TOPIC_EXAMPLES_MAX]
                if str(example).strip()
            ]
            topic = {
                "name": slug[:_TOPIC_NAME_MAX],
                "definition": definition[:_TOPIC_DEFINITION_MAX],
                "type": "DENY",
            }
            if examples:
                topic["examples"] = examples
            topics.append(topic)
        return topics

    @classmethod
    def build_create_guardrail_payload(cls, *, combination_key: str, blocked_slugs: list[str]) -> dict:
        key_digest = hashlib.sha256(combination_key.encode("utf-8")).hexdigest()[:12]
        raw_name = f"nexus-pool-{key_digest}"
        name = re.sub(r"[^0-9a-zA-Z-_]", "-", raw_name)[:_GUARDRAIL_NAME_MAX]

        default_message = settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE
        payload: dict = {
            "name": name,
            "description": f"Nexus guardrail pool for categories: {combination_key}"[:200],
            "blockedInputMessaging": default_message,
            "blockedOutputsMessaging": default_message,
            "contentPolicyConfig": {
                "filtersConfig": list(settings.GUARDRAILS_BEDROCK_CONTENT_FILTERS),
            },
            "sensitiveInformationPolicyConfig": {
                "piiEntitiesConfig": list(settings.GUARDRAILS_BEDROCK_PII_ENTITIES),
            },
        }

        topics = cls.build_topics_config(blocked_slugs)
        if topics:
            payload["topicPolicyConfig"] = {"topicsConfig": topics}

        return payload

    @classmethod
    def get_bedrock_client(cls):
        return boto3.client("bedrock", region_name=settings.AWS_BEDROCK_REGION_NAME)

    @classmethod
    def create_bedrock_guardrail(cls, client, payload: dict) -> tuple[str, str]:
        try:
            response = client.create_guardrail(**payload)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Failed to create Bedrock Guardrail for pool")
            raise BedrockGuardrailPoolError(str(exc)) from exc

        identifier = response.get("guardrailId") or response.get("guardrailArn")
        version = response.get("version") or "DRAFT"
        if not identifier:
            raise BedrockGuardrailPoolError("Bedrock CreateGuardrail returned no guardrailId")
        return str(identifier), str(version)

    @classmethod
    def get_or_create_pool(
        cls,
        category_states: dict[str, bool] | None,
        *,
        client=None,
    ) -> ResolvedGuardrailPool | None:
        """
        Resolve pool for the blocked subset.

        Returns None when no categories are blocked (no Bedrock resource needed).
        """
        blocked_slugs = cls.blocked_slugs_from_states(category_states)
        if not blocked_slugs:
            return None

        key = cls.combination_key(blocked_slugs)
        existing = BedrockGuardrailPool.objects.filter(combination_key=key).first()
        if existing:
            return ResolvedGuardrailPool(pool=existing, created=False)

        bedrock = client or cls.get_bedrock_client()
        payload = cls.build_create_guardrail_payload(combination_key=key, blocked_slugs=blocked_slugs)
        identifier, version = cls.create_bedrock_guardrail(bedrock, payload)

        with transaction.atomic():
            existing = BedrockGuardrailPool.objects.select_for_update().filter(combination_key=key).first()
            if existing:
                return ResolvedGuardrailPool(pool=existing, created=False)

            pool = BedrockGuardrailPool.objects.create(
                combination_key=key,
                category_slugs=blocked_slugs,
                bedrock_guardrail_identifier=identifier,
                bedrock_guardrail_version=version,
            )
            return ResolvedGuardrailPool(pool=pool, created=True)
