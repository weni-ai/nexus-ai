from __future__ import annotations

import hashlib
import logging
import re
import uuid
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
    def _apply_optional_policy_configs(cls, payload: dict) -> None:
        """Attach content/PII policies from settings when configured; omit when empty."""
        content_filters = cls._content_filters_from_settings()
        if content_filters:
            payload["contentPolicyConfig"] = {"filtersConfig": content_filters}

        pii_entities = cls._pii_entities_from_settings()
        if pii_entities:
            payload["sensitiveInformationPolicyConfig"] = {"piiEntitiesConfig": pii_entities}

    @classmethod
    def build_create_guardrail_payload(
        cls,
        *,
        combination_key: str,
        blocked_slugs: list[str],
        name_suffix: str | None = None,
    ) -> dict:
        key_digest = hashlib.sha256(combination_key.encode("utf-8")).hexdigest()[:12]
        raw_name = f"nexus-pool-{key_digest}"
        if name_suffix:
            raw_name = f"{raw_name}-{name_suffix}"
        name = re.sub(r"[^0-9a-zA-Z-_]", "-", raw_name)[:_GUARDRAIL_NAME_MAX]

        from nexus.usecases.guardrails.project_guardrails_config import ProjectGuardrailsConfigUseCase

        default_message = ProjectGuardrailsConfigUseCase.resolve_default_blocking_message()
        payload: dict = {
            "name": name,
            "description": f"Nexus guardrail pool for categories: {combination_key}"[:200],
            "blockedInputMessaging": default_message,
            "blockedOutputsMessaging": default_message,
        }
        cls._apply_optional_policy_configs(payload)

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
    def delete_bedrock_guardrail(cls, client, guardrail_identifier: str) -> None:
        try:
            client.delete_guardrail(guardrailIdentifier=guardrail_identifier)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Failed to delete Bedrock Guardrail %s", guardrail_identifier)
            raise BedrockGuardrailPoolError(str(exc)) from exc

    @classmethod
    def _propagate_pool_assignment(cls, pool: BedrockGuardrailPool, *, identifier: str, version: str) -> int:
        pool.bedrock_guardrail_identifier = identifier
        pool.bedrock_guardrail_version = version
        pool.save(
            update_fields=[
                "bedrock_guardrail_identifier",
                "bedrock_guardrail_version",
                "modified_on",
            ]
        )
        updated = ProjectGuardrailsConfig.objects.filter(bedrock_guardrail_pool=pool).update(
            bedrock_guardrail_identifier=identifier,
            bedrock_guardrail_version=version,
        )
        cls._invalidate_guardrails_cache_for_pool(pool)
        return updated

    @classmethod
    def _invalidate_guardrails_cache_for_pool(cls, pool: BedrockGuardrailPool) -> None:
        """Drop cached ApplyGuardrail identifiers so runtime picks up the new assignment."""
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
                "Failed to invalidate guardrails cache after pool recreate combination_key=%s",
                pool.combination_key,
            )

    @classmethod
    def recreate_pool(cls, pool: BedrockGuardrailPool, *, client=None, delete_old: bool = True) -> str:
        """
        Recreate a Bedrock pool with the current create payload (Denied Topics only
        when baselines are empty). UpdateGuardrail cannot clear content filters, so
        remediation must create a new resource, repoint DB, then delete the old one.
        """
        bedrock = client or cls.get_bedrock_client()
        old_identifier = pool.bedrock_guardrail_identifier

        blocked_slugs = list(pool.category_slugs or [])
        if not blocked_slugs and pool.combination_key:
            blocked_slugs = [slug for slug in pool.combination_key.split("|") if slug]

        # Unique name so Create succeeds while the old guardrail still exists.
        payload = cls.build_create_guardrail_payload(
            combination_key=pool.combination_key,
            blocked_slugs=blocked_slugs,
            name_suffix=uuid.uuid4().hex[:8],
        )
        new_identifier, version = cls.create_bedrock_guardrail(bedrock, payload)

        with transaction.atomic():
            cls._propagate_pool_assignment(pool, identifier=new_identifier, version=version)

        if delete_old and old_identifier and old_identifier != new_identifier:
            try:
                cls.delete_bedrock_guardrail(bedrock, old_identifier)
            except BedrockGuardrailPoolError:
                logger.warning(
                    "Pool recreated but old Bedrock guardrail was not deleted "
                    "combination_key=%s old_id=%s new_id=%s",
                    pool.combination_key,
                    old_identifier,
                    new_identifier,
                )

        return version

    @classmethod
    def sync_pool_policies(cls, pool: BedrockGuardrailPool, *, client=None, **_kwargs) -> str:
        """Backward-compatible alias: remediation recreates the Bedrock resource."""
        return cls.recreate_pool(pool, client=client)

    @classmethod
    def sync_all_pool_policies(cls, *, client=None, **_kwargs) -> list[tuple[str, str]]:
        """Recreate every registered pool. Returns list of (combination_key, new_version)."""
        bedrock = client or cls.get_bedrock_client()
        results: list[tuple[str, str]] = []
        for pool in BedrockGuardrailPool.objects.order_by("id"):
            version = cls.recreate_pool(pool, client=bedrock)
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
