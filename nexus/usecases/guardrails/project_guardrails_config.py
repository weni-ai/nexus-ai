from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import boto3
import sentry_sdk
from django.conf import settings
from django.core.exceptions import ValidationError

from nexus.projects.models import Project, ProjectGuardrailsConfig
from nexus.usecases.guardrails.bedrock_guardrail_pool import (
    BedrockGuardrailPoolError,
    BedrockGuardrailPoolService,
)

_UNSET = object()
logger = logging.getLogger(__name__)


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _latency_scenario(blocked_count: int, catalog_count: int) -> str:
    """Label blocked-category density for latency comparisons."""
    if blocked_count <= 0:
        return "none_blocked"
    if blocked_count == 1:
        return "one_blocked"
    if catalog_count > 0 and blocked_count >= catalog_count:
        return "all_blocked"
    return "partial_blocked"


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
        config, created = ProjectGuardrailsConfig.objects.get_or_create(
            project=project,
            defaults={
                "category_states": cls.build_default_category_states(blocked=True),
                "blocking_message": None,
                "initialized_as_new_project": True,
            },
        )
        if not created:
            default_blocked = config.initialized_as_new_project
            merged_states = cls.merge_category_states(config.category_states, default_blocked=default_blocked)
            if merged_states != config.category_states:
                config.category_states = merged_states
                config.save(update_fields=["category_states", "modified_on"])

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
    def blocked_category_count(cls, category_states: dict[str, bool] | None) -> int:
        if not category_states:
            return 0
        return sum(1 for slug in cls.catalog_slugs() if category_states.get(slug) is True)

    @classmethod
    def catalog_category_count(cls) -> int:
        return len(cls.catalog_slugs())

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
                "blocked_category_count": 0,
                "catalog_category_count": cls.catalog_category_count(),
            }

        config = cls.get_or_initialize(project)
        message, _ = cls.effective_blocking_message(config)
        states = config.category_states or {}
        blocked_count = cls.blocked_category_count(states)
        catalog_count = cls.catalog_category_count()
        return {
            "guardrailIdentifier": config.bedrock_guardrail_identifier or None,
            "guardrailVersion": config.bedrock_guardrail_version or None,
            "blocking_message": message,
            "has_blocked_category": blocked_count > 0,
            "blocked_category_count": blocked_count,
            "catalog_category_count": catalog_count,
        }

    @classmethod
    def _log_apply_latency(
        cls,
        *,
        outcome: str,
        started_at: float,
        runtime_config: dict | None,
        text: str | None = None,
        bedrock_processing_ms: int | float | None = None,
        action: str | None = None,
    ) -> None:
        catalog_count = int((runtime_config or {}).get("catalog_category_count") or cls.catalog_category_count())
        if runtime_config and "blocked_category_count" in runtime_config:
            blocked_count = int(runtime_config.get("blocked_category_count") or 0)
        elif runtime_config and runtime_config.get("has_blocked_category"):
            # Legacy cache payload without count — still label as blocked.
            blocked_count = -1
        else:
            blocked_count = 0

        scenario = "blocked_unknown_count" if blocked_count < 0 else _latency_scenario(blocked_count, catalog_count)
        logger.info(
            "guardrails_latency event=apply_input outcome=%s scenario=%s "
            "blocked_count=%s catalog_count=%s duration_ms=%.2f "
            "bedrock_processing_ms=%s action=%s text_chars=%s",
            outcome,
            scenario,
            blocked_count if blocked_count >= 0 else "unknown",
            catalog_count,
            _elapsed_ms(started_at),
            bedrock_processing_ms if bedrock_processing_ms is not None else "-",
            action or "-",
            len(text) if text else 0,
        )

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
        started_at = time.perf_counter()

        if not text or not text.strip():
            cls._log_apply_latency(
                outcome="skipped_empty_text",
                started_at=started_at,
                runtime_config=runtime_config,
                text=text,
            )
            return None
        if not runtime_config:
            cls._log_apply_latency(
                outcome="skipped_missing_config",
                started_at=started_at,
                runtime_config=runtime_config,
                text=text,
            )
            return None
        if not runtime_config.get("has_blocked_category"):
            cls._log_apply_latency(
                outcome="skipped_none_blocked",
                started_at=started_at,
                runtime_config=runtime_config,
                text=text,
            )
            return None

        identifier = runtime_config.get("guardrailIdentifier")
        version = runtime_config.get("guardrailVersion")
        if not identifier or not version:
            logger.info(
                "Skipping ApplyGuardrail: categories blocked but no pool identifier/version assigned",
            )
            cls._log_apply_latency(
                outcome="skipped_missing_pool",
                started_at=started_at,
                runtime_config=runtime_config,
                text=text,
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
            cls._log_apply_latency(
                outcome="fail_open",
                started_at=started_at,
                runtime_config=runtime_config,
                text=text,
            )
            return None

        assessments = response.get("assessments") or []
        bedrock_processing_ms = None
        if assessments and isinstance(assessments[0], dict):
            invocation_metrics = assessments[0].get("invocationMetrics") or {}
            bedrock_processing_ms = invocation_metrics.get("guardrailProcessingLatency")
        if bedrock_processing_ms is None:
            top_metrics = response.get("invocationMetrics") or response.get("usage") or {}
            if isinstance(top_metrics, dict):
                bedrock_processing_ms = top_metrics.get("guardrailProcessingLatency")

        action = response.get("action")
        if action != "GUARDRAIL_INTERVENED":
            cls._log_apply_latency(
                outcome="allowed",
                started_at=started_at,
                runtime_config=runtime_config,
                text=text,
                bedrock_processing_ms=bedrock_processing_ms,
                action=action,
            )
            return None

        cls._log_apply_latency(
            outcome="intervened",
            started_at=started_at,
            runtime_config=runtime_config,
            text=text,
            bedrock_processing_ms=bedrock_processing_ms,
            action=action,
        )
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
