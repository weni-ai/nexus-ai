import logging

from django.contrib import admin
from django.contrib.postgres.fields import ArrayField
from django.db import models

from nexus.admin_widgets import PrettyJSONWidget
from nexus.inline_agents.backends.bedrock.models import Supervisor
from nexus.inline_agents.backends.openai.models import OpenAISupervisor
from nexus.inline_agents.models import Agent, Guardrail, InlineAgentsConfiguration

logger = logging.getLogger(__name__)


@admin.register(Guardrail)
class GuardrailAdmin(admin.ModelAdmin):
    list_display = ("identifier", "version", "created_on", "current_version")
    list_filter = ("current_version", "identifier")
    search_fields = ("identifier", "changelog")
    readonly_fields = ("created_on",)
    ordering = ("-created_on",)

    fieldsets = (
        (None, {"fields": ("identifier", "version", "current_version")}),
        ("Content", {"fields": ("changelog",)}),
        ("Metadata", {"fields": ("created_on",), "classes": ("collapse",)}),
    )


@admin.register(Supervisor)
class SupervisorAdmin(admin.ModelAdmin):
    list_display = ("name", "foundation_model", "created_on")
    list_filter = ("foundation_model",)
    search_fields = ("name", "instruction")
    readonly_fields = ("created_on",)
    ordering = ("-created_on",)

    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 20, "cols": 80, "class": "vLargeTextField"})},
    }

    fieldsets = (
        (None, {"fields": ("name", "foundation_model", "instruction")}),
        ("Configuration", {"fields": ("prompt_override_configuration", "action_groups", "knowledge_bases")}),
        (
            "Human Support",
            {"fields": ("human_support_prompt", "human_support_action_groups"), "classes": ("collapse",)},
        ),
        ("Components", {"fields": ("components_prompt", "components_human_support_prompt"), "classes": ("collapse",)}),
        ("Metadata", {"fields": ("created_on",), "classes": ("collapse",)}),
    )


@admin.register(OpenAISupervisor)
class OpenAISupervisorAdmin(admin.ModelAdmin):
    list_display = ("name", "foundation_model", "created_on")
    list_filter = ("foundation_model",)
    search_fields = ("name", "instruction")
    readonly_fields = ("created_on",)
    ordering = ("-created_on",)

    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 20, "cols": 80, "class": "vLargeTextField"})},
        ArrayField: {"widget": PrettyJSONWidget(attrs={"rows": 10, "cols": 80, "class": "aLargeTextField"})},
    }

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "foundation_model",
                    "instruction",
                    "default_instructions_for_collaborators",
                    "max_tokens",
                    "exclude_tools_from_audio_orchestration",
                    "exclude_tools_from_text_orchestration",
                )
            },
        ),
        ("Transcription", {"fields": ("transcription_prompt",), "classes": ("collapse",)}),
        (
            "Configuration",
            {"fields": ("prompt_override_configuration", "action_groups", "knowledge_bases"), "classes": ("collapse",)},
        ),
        (
            "Human Support",
            {"fields": ("human_support_prompt", "human_support_action_groups"), "classes": ("collapse",)},
        ),
        (
            "Components",
            {
                "fields": ("components_prompt", "components_human_support_prompt", "components_instructions_up_prompt"),
                "classes": ("collapse",),
            },
        ),
        ("Metadata", {"fields": ("created_on",), "classes": ("collapse",)}),
    )

    def save_model(self, request, obj, form, change):
        """Save model and trigger cache invalidation."""
        super().save_model(request, obj, form, change)

        # Invalidate OpenAI Supervisor cache
        try:
            from router.services.openai_supervisor_cache_service import OpenAISupervisorCacheService

            cache_service = OpenAISupervisorCacheService()
            cache_service.invalidate_cache(refresh=True)
            logger.info(f"[Admin] Invalidated OpenAI Supervisor cache (ID: {obj.id}, Name: {obj.name})")
        except Exception as e:
            logger.warning(f"[Admin] Failed to invalidate OpenAI Supervisor cache: {e}")

    def delete_model(self, request, obj):
        """Delete model and trigger cache invalidation."""
        supervisor_id = obj.id
        supervisor_name = obj.name

        super().delete_model(request, obj)

        # Invalidate OpenAI Supervisor cache after deletion
        try:
            from router.services.openai_supervisor_cache_service import OpenAISupervisorCacheService

            cache_service = OpenAISupervisorCacheService()
            cache_service.invalidate_cache(refresh=True)
            logger.info(f"[Admin] Invalidated OpenAI Supervisor cache after deletion (ID: {supervisor_id}, Name: {supervisor_name})")
        except Exception as e:
            logger.warning(f"[Admin] Failed to invalidate OpenAI Supervisor cache after deletion: {e}")


@admin.register(InlineAgentsConfiguration)
class InlineAgentsConfigurationAdmin(admin.ModelAdmin):
    list_display = ("project", "agents_backend", "default_instructions_for_collaborators")
    list_filter = ("agents_backend",)
    search_fields = ("project__name", "project__uuid", "agents_backend")
    ordering = ("project__name",)
    autocomplete_fields = ["project"]

    fieldsets = ((None, {"fields": ("project", "agents_backend", "default_instructions_for_collaborators")}),)

    def save_model(self, request, obj, form, change):
        """Save model and trigger cache invalidation."""
        super().save_model(request, obj, form, change)

        # Fire cache invalidation event for project update (inline_agent_config is part of project cache)
        try:
            from nexus.events import notify_async

            notify_async(
                event="cache_invalidation:project",
                project=obj.project,
            )
            logger.info(
                f"[Admin] Triggered cache invalidation for InlineAgentsConfiguration (project {obj.project.uuid})"
            )
        except Exception as e:
            logger.warning(f"[Admin] Failed to trigger cache invalidation for InlineAgentsConfiguration: {e}")


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("uuid", "name", "project", "is_official")
    list_filter = ("is_official", "source_type")
    search_fields = ("name", "project__name", "project__uuid", "slug")
    ordering = ("project__name",)
    autocomplete_fields = ["project"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "project",
                    "is_official",
                    "instruction",
                    "collaboration_instructions",
                    "foundation_model",
                    "backend_foundation_models",
                    "source_type",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """Save model and trigger cache invalidation."""
        super().save_model(request, obj, form, change)

        # Fire cache invalidation event for team update (agents are part of team)
        try:
            from nexus.events import notify_async

            project_uuid = str(obj.project.uuid)
            notify_async(
                event="cache_invalidation:team",
                project_uuid=project_uuid,
            )
            logger.info(f"[Admin] Triggered cache invalidation for Agent {obj.name} (project {project_uuid})")
        except Exception as e:
            logger.warning(f"[Admin] Failed to trigger cache invalidation for Agent: {e}")

    def delete_model(self, request, obj):
        """Delete model and trigger cache invalidation."""
        project_uuid = str(obj.project.uuid) if obj.project else None

        super().delete_model(request, obj)

        # Fire cache invalidation event for team update
        if project_uuid:
            try:
                from nexus.events import notify_async

                notify_async(
                    event="cache_invalidation:team",
                    project_uuid=project_uuid,
                )
                logger.info(f"[Admin] Triggered cache invalidation after Agent deletion (project {project_uuid})")
            except Exception as e:
                logger.warning(f"[Admin] Failed to trigger cache invalidation after Agent deletion: {e}")
