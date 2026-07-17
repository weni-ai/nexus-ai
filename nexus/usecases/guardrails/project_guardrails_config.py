from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from nexus.projects.models import Project, ProjectGuardrailsConfig


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
    def get_or_initialize(cls, project: Project) -> ProjectGuardrailsConfig:
        default_blocked = cls.default_blocked_for_project(project)
        config, created = ProjectGuardrailsConfig.objects.get_or_create(
            project=project,
            defaults={
                "category_states": cls.build_default_category_states(blocked=default_blocked),
                "blocking_message": None,
                "initialized_as_new_project": default_blocked,
            },
        )
        if created:
            return config

        default_blocked = config.initialized_as_new_project
        merged_states = cls.merge_category_states(config.category_states, default_blocked=default_blocked)
        if merged_states != config.category_states:
            config.category_states = merged_states
            config.save(update_fields=["category_states", "modified_on"])

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
