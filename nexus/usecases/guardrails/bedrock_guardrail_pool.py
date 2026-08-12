from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction

from nexus.projects.models import BedrockGuardrailPool, ProjectGuardrailsConfig

logger = logging.getLogger(__name__)

# Bedrock Denied Topic constraints (API)
_TOPIC_NAME_MAX = 100
_TOPIC_DEFINITION_MAX = 200
_TOPIC_EXAMPLE_MAX = 100
_TOPIC_EXAMPLES_MAX = 5
_GUARDRAIL_NAME_MAX = 50

_CONTENT_FILTER_TYPES_TO_DISABLE = (
    "SEXUAL",
    "VIOLENCE",
    "HATE",
    "INSULTS",
    "MISCONDUCT",
    "PROMPT_ATTACK",
)

# PII types. Bedrock rejects empty
_PII_ENTITY_TYPES_TO_DISABLE = (
    "EMAIL",
    "PHONE",
    "CREDIT_DEBIT_CARD_NUMBER",
    "ADDRESS",
)


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
    def _content_filters_from_settings(cls) -> list[dict]:
        return list(getattr(settings, "GUARDRAILS_BEDROCK_CONTENT_FILTERS", None) or [])

    @classmethod
    def _pii_entities_from_settings(cls) -> list[dict]:
        return list(getattr(settings, "GUARDRAILS_BEDROCK_PII_ENTITIES", None) or [])

    @classmethod
    def _disabled_content_filters(cls) -> list[dict]:
        filters: list[dict] = []
        for filter_type in _CONTENT_FILTER_TYPES_TO_DISABLE:
            entry = {
                "type": filter_type,
                "inputStrength": "NONE",
                "outputStrength": "NONE",
            }
            filters.append(entry)
        return filters

    @classmethod
    def _disabled_pii_entities(cls, existing_types: list[str] | None = None) -> list[dict]:
        """
        Build a non-empty piiEntitiesConfig that turns PII filtering off.

        UpdateGuardrail requires min length 1 for piiEntitiesConfig when the
        sensitiveInformationPolicyConfig object is sent; empty lists are rejected.
        """
        types = [t for t in (existing_types or []) if t]
        if not types:
            types = list(_PII_ENTITY_TYPES_TO_DISABLE)
        # Preserve order, drop duplicates.
        seen: set[str] = set()
        ordered: list[str] = []
        for entity_type in types:
            if entity_type not in seen:
                seen.add(entity_type)
                ordered.append(entity_type)
        return [
            {
                "type": entity_type,
                "action": "NONE",
                "inputAction": "NONE",
                "outputAction": "NONE",
                "inputEnabled": False,
                "outputEnabled": False,
            }
            for entity_type in ordered
        ]

    @classmethod
    def _pii_types_from_guardrail(cls, guardrail: dict | None) -> list[str]:
        if not guardrail:
            return []
        policy = guardrail.get("sensitiveInformationPolicy") or {}
        entities = policy.get("piiEntities") or []
        types: list[str] = []
        for entry in entities:
            entity_type = entry.get("type") if isinstance(entry, dict) else None
            if entity_type:
                types.append(str(entity_type))
        return types

    @classmethod
    def _apply_optional_policy_configs(
        cls,
        payload: dict,
        *,
        for_update: bool = False,
        existing_pii_types: list[str] | None = None,
    ) -> None:
        """
        Attach content/PII policies from settings when configured.

        On create: omit empty policies so Bedrock does not enable them.
        On update: when settings are empty, explicitly disable residual content
        filters and disable PII entities (action NONE; never send empty lists).
        """
        content_filters = cls._content_filters_from_settings()
        if content_filters:
            payload["contentPolicyConfig"] = {"filtersConfig": content_filters}
        elif for_update:
            payload["contentPolicyConfig"] = {"filtersConfig": cls._disabled_content_filters()}

        pii_entities = cls._pii_entities_from_settings()
        if pii_entities:
            payload["sensitiveInformationPolicyConfig"] = {"piiEntitiesConfig": pii_entities}
        elif for_update:
            payload["sensitiveInformationPolicyConfig"] = {
                "piiEntitiesConfig": cls._disabled_pii_entities(existing_pii_types),
            }

    @classmethod
    def build_create_guardrail_payload(cls, *, combination_key: str, blocked_slugs: list[str]) -> dict:
        key_digest = hashlib.sha256(combination_key.encode("utf-8")).hexdigest()[:12]
        raw_name = f"nexus-pool-{key_digest}"
        name = re.sub(r"[^0-9a-zA-Z-_]", "-", raw_name)[:_GUARDRAIL_NAME_MAX]

        from nexus.usecases.guardrails.project_guardrails_config import ProjectGuardrailsConfigUseCase

        default_message = ProjectGuardrailsConfigUseCase.resolve_default_blocking_message()
        payload: dict = {
            "name": name,
            "description": f"Nexus guardrail pool for categories: {combination_key}"[:200],
            "blockedInputMessaging": default_message,
            "blockedOutputsMessaging": default_message,
        }
        cls._apply_optional_policy_configs(payload, for_update=False)

        topics = cls.build_topics_config(blocked_slugs)
        if topics:
            payload["topicPolicyConfig"] = {"topicsConfig": topics}

        return payload

    @classmethod
    def build_update_guardrail_payload(
        cls,
        *,
        guardrail_identifier: str,
        name: str,
        blocked_input_messaging: str,
        blocked_outputs_messaging: str,
        blocked_slugs: list[str],
        description: str | None = None,
        existing_pii_types: list[str] | None = None,
    ) -> dict:
        payload: dict = {
            "guardrailIdentifier": guardrail_identifier,
            "name": name,
            "blockedInputMessaging": blocked_input_messaging,
            "blockedOutputsMessaging": blocked_outputs_messaging,
        }
        if description:
            payload["description"] = description[:200]

        cls._apply_optional_policy_configs(
            payload,
            for_update=True,
            existing_pii_types=existing_pii_types,
        )

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
    def get_bedrock_guardrail(cls, client, guardrail_identifier: str) -> dict:
        try:
            return client.get_guardrail(guardrailIdentifier=guardrail_identifier)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Failed to get Bedrock Guardrail %s", guardrail_identifier)
            raise BedrockGuardrailPoolError(str(exc)) from exc

    @classmethod
    def update_bedrock_guardrail(cls, client, payload: dict) -> str:
        try:
            response = client.update_guardrail(**payload)
        except (ClientError, BotoCoreError) as exc:
            logger.exception(
                "Failed to update Bedrock Guardrail %s",
                payload.get("guardrailIdentifier"),
            )
            raise BedrockGuardrailPoolError(str(exc)) from exc
        return str(response.get("version") or "DRAFT")

    @classmethod
    def create_bedrock_guardrail_version(cls, client, guardrail_identifier: str, *, description: str) -> str:
        try:
            response = client.create_guardrail_version(
                guardrailIdentifier=guardrail_identifier,
                description=description[:200],
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Failed to publish Bedrock Guardrail version for %s", guardrail_identifier)
            raise BedrockGuardrailPoolError(str(exc)) from exc

        version = response.get("version")
        if not version:
            raise BedrockGuardrailPoolError("Bedrock CreateGuardrailVersion returned no version")
        return str(version)

    @classmethod
    def _propagate_pool_version(cls, pool: BedrockGuardrailPool, version: str) -> int:
        pool.bedrock_guardrail_version = version
        pool.save(update_fields=["bedrock_guardrail_version", "modified_on"])
        configs = ProjectGuardrailsConfig.objects.filter(bedrock_guardrail_pool=pool).select_related("project")
        updated = configs.update(
            bedrock_guardrail_identifier=pool.bedrock_guardrail_identifier,
            bedrock_guardrail_version=version,
        )
        cls._invalidate_guardrails_cache_for_pool(pool)
        return updated

    @classmethod
    def _invalidate_guardrails_cache_for_pool(cls, pool: BedrockGuardrailPool) -> None:
        """Drop cached ApplyGuardrail identifiers so runtime picks up the new version."""
        project_uuids = (
            ProjectGuardrailsConfig.objects.filter(bedrock_guardrail_pool=pool)
            .values_list("project__uuid", flat=True)
            .distinct()
        )
        if not project_uuids:
            return
        try:
            from router.services.cache_service import CacheService

            cache_service = CacheService()
            for project_uuid in project_uuids:
                if project_uuid:
                    cache_service.invalidate_guardrails_cache(str(project_uuid))
        except Exception:
            logger.exception(
                "Failed to invalidate guardrails cache after pool sync combination_key=%s",
                pool.combination_key,
            )

    @classmethod
    def sync_pool_policies(cls, pool: BedrockGuardrailPool, *, client=None, publish_version: bool = True) -> str:
        """
        Align an existing Bedrock pool with current settings (topics + optional baselines).

        Clears residual content filters / PII when settings lists are empty, keeps
        Denied Topics for the pool combination, and publishes a new version so
        ApplyGuardrail picks up the change.
        """
        bedrock = client or cls.get_bedrock_client()
        identifier = pool.bedrock_guardrail_identifier
        current = cls.get_bedrock_guardrail(bedrock, identifier)

        blocked_slugs = list(pool.category_slugs or [])
        if not blocked_slugs and pool.combination_key:
            blocked_slugs = [slug for slug in pool.combination_key.split("|") if slug]

        payload = cls.build_update_guardrail_payload(
            guardrail_identifier=identifier,
            name=str(current.get("name") or f"nexus-pool-{pool.pk}")[:_GUARDRAIL_NAME_MAX],
            blocked_input_messaging=str(current.get("blockedInputMessaging") or "Blocked."),
            blocked_outputs_messaging=str(current.get("blockedOutputsMessaging") or "Blocked."),
            blocked_slugs=blocked_slugs,
            description=current.get("description"),
            existing_pii_types=cls._pii_types_from_guardrail(current),
        )
        cls.update_bedrock_guardrail(bedrock, payload)

        if publish_version:
            version = cls.create_bedrock_guardrail_version(
                bedrock,
                identifier,
                description=f"Sync pool policies for {pool.combination_key}",
            )
        else:
            version = "DRAFT"

        with transaction.atomic():
            cls._propagate_pool_version(pool, version)
        return version

    @classmethod
    def sync_all_pool_policies(cls, *, client=None, publish_version: bool = True) -> list[tuple[str, str]]:
        """Sync every registered pool. Returns list of (combination_key, new_version)."""
        bedrock = client or cls.get_bedrock_client()
        results: list[tuple[str, str]] = []
        for pool in BedrockGuardrailPool.objects.order_by("id"):
            version = cls.sync_pool_policies(pool, client=bedrock, publish_version=publish_version)
            results.append((pool.combination_key, version))
        return results

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
