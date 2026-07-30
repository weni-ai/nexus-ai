from __future__ import annotations

import logging
from dataclasses import dataclass

import boto3
import sentry_sdk
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from nexus.projects.models import Project, ProjectGuardrailsConfig
from nexus.usecases.guardrails.bedrock_guardrail_pool import (
    BedrockGuardrailPoolError,
    BedrockGuardrailPoolService,
)

_UNSET = object()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuardrailsConfigPayload:
    categories: list[dict]
    blocking_message: str
    blocking_message_is_custom: bool
    writable: bool

    def as_dict(self) -> dict:
        return {
            "categories": self.categories,
            "blocking_message": self.blocking_message,
            "blocking_message_is_custom": self.blocking_message_is_custom,
            "writable": self.writable,
        }


class ProjectGuardrailsConfigUseCase:
    @staticmethod
    def catalog() -> list[dict[str, str]]:
        return list(settings.GUARDRAIL_CATEGORY_CATALOG)

    @staticmethod
    def catalog_slugs() -> list[str]:
        return [entry["slug"] for entry in settings.GUARDRAIL_CATEGORY_CATALOG]

    @classmethod
    def is_new_project(cls, project: Project) -> bool:
        deploy_at = settings.GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT
        created_at = project.created_at
        if timezone.is_naive(created_at):
            created_at = timezone.make_aware(created_at, timezone.get_current_timezone())
        if timezone.is_naive(deploy_at):
            deploy_at = timezone.make_aware(deploy_at, timezone.get_current_timezone())
        return created_at >= deploy_at

    @classmethod
    def default_blocked_for_project(cls, project: Project) -> bool:
        return cls.is_new_project(project)

    @classmethod
    def build_default_category_states(cls, *, blocked: bool) -> dict[str, bool]:
        return {slug: blocked for slug in cls.catalog_slugs()}

    @classmethod
    def sanitize_category_states(cls, category_states: dict | None) -> dict[str, bool]:
        if not category_states:
            return {}

        allowed = set(cls.catalog_slugs())
        sanitized: dict[str, bool] = {}
        for slug, blocked in category_states.items():
            if slug in allowed and isinstance(blocked, bool):
                sanitized[slug] = blocked
        return sanitized

    @classmethod
    def merge_category_states(
        cls,
        stored_states: dict[str, bool] | None,
        *,
        default_blocked: bool,
    ) -> dict[str, bool]:
        merged = cls.build_default_category_states(blocked=default_blocked)
        merged.update(cls.sanitize_category_states(stored_states))
        return merged

    @classmethod
    def get_or_initialize(cls, project: Project, *, assign_pool: bool = True) -> ProjectGuardrailsConfig:
        default_blocked = cls.default_blocked_for_project(project)
        config, created = ProjectGuardrailsConfig.objects.get_or_create(
            project=project,
            defaults={
                "category_states": cls.build_default_category_states(blocked=default_blocked),
                "blocking_message": None,
                "initialized_as_new_project": default_blocked,
            },
        )
        if not created:
            default_blocked = config.initialized_as_new_project
            merged_states = cls.merge_category_states(config.category_states, default_blocked=default_blocked)
            if merged_states != config.category_states:
                config.category_states = merged_states
                config.save(update_fields=["category_states", "modified_on"])

        # GET/runtime assign the pool for blocked defaults. update_config uses
        # assign_pool=False so message-only PATCH never resolves/creates Bedrock pools.
        if assign_pool:
            return cls.ensure_pool_assignment(config)
        return config

    @classmethod
    def ensure_pool_assignment(cls, config: ProjectGuardrailsConfig) -> ProjectGuardrailsConfig:
        """
        Resolve and persist the Bedrock pool when categories are blocked but no
        identifier/version is assigned yet.

        Fail-open on Bedrock errors so GET / lazy init does not fail the request.
        """
        if not cls.has_blocked_category(config.category_states or {}):
            return config
        if config.bedrock_guardrail_identifier and config.bedrock_guardrail_version:
            return config

        blocked_slugs = BedrockGuardrailPoolService.blocked_slugs_from_states(config.category_states)
        combination_key = BedrockGuardrailPoolService.combination_key(blocked_slugs)
        try:
            resolved = BedrockGuardrailPoolService.get_or_create_pool(config.category_states)
        except BedrockGuardrailPoolError as exc:
            logger.exception(
                "Failed to assign Bedrock pool on lazy init (fail-open) project_uuid=%s combination_key=%s",
                config.project_id,
                combination_key,
            )
            sentry_sdk.capture_exception(exc)
            return config

        if resolved is None:
            return config

        config.bedrock_guardrail_pool = resolved.pool
        config.bedrock_guardrail_identifier = resolved.pool.bedrock_guardrail_identifier
        config.bedrock_guardrail_version = resolved.pool.bedrock_guardrail_version
        config.save(
            update_fields=[
                "bedrock_guardrail_pool",
                "bedrock_guardrail_identifier",
                "bedrock_guardrail_version",
                "modified_on",
            ]
        )
        return config

    @classmethod
    def effective_blocking_message(cls, config: ProjectGuardrailsConfig) -> tuple[str, bool]:
        if config.blocking_message is not None and config.blocking_message.strip():
            return config.blocking_message, True
        return settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE, False

    @classmethod
    def has_blocked_category(cls, category_states: dict[str, bool]) -> bool:
        return any(category_states.get(slug, False) for slug in cls.catalog_slugs())

    @classmethod
    def validate_blocking_message_for_states(
        cls,
        blocking_message: str | None,
        category_states: dict[str, bool],
    ) -> None:
        if not cls.has_blocked_category(category_states):
            return

        effective_message = blocking_message
        if effective_message is None or not effective_message.strip():
            effective_message = settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE

        if not effective_message or not effective_message.strip():
            raise ValidationError({"blocking_message": "Blocking message is required when any category is blocked."})

        if len(effective_message) > ProjectGuardrailsConfig.BLOCKING_MESSAGE_MAX_LENGTH:
            raise ValidationError(
                {
                    "blocking_message": (
                        f"Blocking message must be at most "
                        f"{ProjectGuardrailsConfig.BLOCKING_MESSAGE_MAX_LENGTH} characters."
                    )
                }
            )

    @classmethod
    def validate_category_states(cls, category_states: dict) -> dict[str, bool]:
        if not isinstance(category_states, dict):
            raise ValidationError({"category_states": "category_states must be an object."})

        unknown_slugs = sorted(set(category_states) - set(cls.catalog_slugs()))
        if unknown_slugs:
            raise ValidationError({"category_states": f"Unknown guardrail categories: {', '.join(unknown_slugs)}"})

        for slug, blocked in category_states.items():
            if not isinstance(blocked, bool):
                raise ValidationError({"category_states": f"Blocked state for '{slug}' must be a boolean."})

        return cls.sanitize_category_states(category_states)

    @classmethod
    def build_categories_response(cls, category_states: dict[str, bool]) -> list[dict]:
        return [
            {
                "slug": entry["slug"],
                "blocked": bool(category_states.get(entry["slug"], False)),
            }
            for entry in cls.catalog()
        ]

    @classmethod
    def to_payload(cls, config: ProjectGuardrailsConfig, *, writable: bool) -> GuardrailsConfigPayload:
        message, is_custom = cls.effective_blocking_message(config)
        return GuardrailsConfigPayload(
            categories=cls.build_categories_response(config.category_states),
            blocking_message=message,
            blocking_message_is_custom=is_custom,
            writable=writable,
        )

    @classmethod
    def get_runtime_config_as_dict(cls, project_uuid: str) -> dict:
        """
        Cache-friendly runtime payload for ApplyGuardrail preprocess.

        Lazy-initializes config so new-project defaults can apply without requiring
        a prior visit to the guardrails config API.
        """
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            return {
                "guardrailIdentifier": None,
                "guardrailVersion": None,
                "blocking_message": None,
                "has_blocked_category": False,
            }

        config = cls.get_or_initialize(project)
        message, _ = cls.effective_blocking_message(config)
        return {
            "guardrailIdentifier": config.bedrock_guardrail_identifier or None,
            "guardrailVersion": config.bedrock_guardrail_version or None,
            "blocking_message": message,
            "has_blocked_category": cls.has_blocked_category(config.category_states or {}),
        }

    @classmethod
    def apply_input_guardrail(
        cls,
        text: str,
        runtime_config: dict | None,
        *,
        client=None,
    ) -> str | None:
        """
        Evaluate user input with Bedrock ApplyGuardrail (source=INPUT).

        Returns the project effective blocking message on GUARDRAIL_INTERVENED (Option A).
        Returns None when the check is skipped or the input is allowed.
        Fail-open on AWS errors (log + Sentry).
        """
        if not text or not text.strip():
            return None
        if not runtime_config:
            return None
        if not runtime_config.get("has_blocked_category"):
            return None

        identifier = runtime_config.get("guardrailIdentifier")
        version = runtime_config.get("guardrailVersion")
        if not identifier or not version:
            logger.info(
                "Skipping ApplyGuardrail: categories blocked but no pool identifier/version assigned",
            )
            return None

        bedrock = client or boto3.client("bedrock-runtime", region_name=settings.AWS_BEDROCK_REGION_NAME)
        try:
            response = bedrock.apply_guardrail(
                guardrailIdentifier=str(identifier),
                guardrailVersion=str(version),
                source="INPUT",
                content=[{"text": {"text": text}}],
            )
        except Exception as exc:
            logger.exception("ApplyGuardrail failed; allowing message (fail-open)")
            sentry_sdk.capture_exception(exc)
            return None

        if response.get("action") != "GUARDRAIL_INTERVENED":
            return None

        # Option A: ignore Bedrock canned outputs; use project effective message.
        return runtime_config.get("blocking_message") or settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE

    @classmethod
    def update_config(
        cls,
        project: Project,
        *,
        category_states: dict | None = None,
        blocking_message: str | None = _UNSET,
    ) -> ProjectGuardrailsConfig:
        config = cls.get_or_initialize(project, assign_pool=False)
        previous_states = dict(config.category_states)
        next_states = dict(previous_states)

        if category_states is not None:
            validated_partial = cls.validate_category_states(category_states)
            next_states.update(validated_partial)
            next_states = cls.merge_category_states(
                next_states,
                default_blocked=config.initialized_as_new_project,
            )

        next_blocking_message = config.blocking_message
        if blocking_message is not _UNSET:
            if blocking_message is None:
                next_blocking_message = None
            elif isinstance(blocking_message, str):
                stripped = blocking_message.strip()
                next_blocking_message = stripped if stripped else None
            else:
                raise ValidationError({"blocking_message": "Blocking message must be a string or null."})

        cls.validate_blocking_message_for_states(next_blocking_message, next_states)

        category_states_changed = next_states != config.category_states
        blocking_message_changed = blocking_message is not _UNSET and next_blocking_message != config.blocking_message

        # Message-only PATCH must not resolve/create Bedrock pools (FR-023).
        pool_to_assign = None
        pool_identifier = None
        pool_version = None
        if category_states_changed:
            # Resolve before local save so Bedrock failure leaves config unchanged.
            resolved = BedrockGuardrailPoolService.get_or_create_pool(next_states)
            if resolved is not None:
                pool_to_assign = resolved.pool
                pool_identifier = resolved.pool.bedrock_guardrail_identifier
                pool_version = resolved.pool.bedrock_guardrail_version

        if category_states_changed or blocking_message_changed:
            update_fields = ["modified_on"]
            if category_states_changed:
                config.category_states = next_states
                config.bedrock_guardrail_pool = pool_to_assign
                config.bedrock_guardrail_identifier = pool_identifier
                config.bedrock_guardrail_version = pool_version
                update_fields.extend(
                    [
                        "category_states",
                        "bedrock_guardrail_pool",
                        "bedrock_guardrail_identifier",
                        "bedrock_guardrail_version",
                    ]
                )
            if blocking_message_changed:
                config.blocking_message = next_blocking_message
                update_fields.append("blocking_message")
            config.save(update_fields=update_fields)

        return config
