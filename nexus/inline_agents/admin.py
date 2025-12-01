from django.contrib import admin, messages
from django.contrib.postgres.fields import ArrayField
from django.db import models

from nexus.admin_widgets import PrettyJSONWidget
from nexus.inline_agents.backends.bedrock.models import Supervisor
from nexus.inline_agents.backends.openai.models import OpenAISupervisor
from nexus.inline_agents.models import (
    Agent,
    AgentCategory,
    AgentGroup,
    AgentSystem,
    AgentType,
    Guardrail,
    InlineAgentsConfiguration,
)


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


@admin.register(InlineAgentsConfiguration)
class InlineAgentsConfigurationAdmin(admin.ModelAdmin):
    list_display = ("project", "agents_backend", "default_instructions_for_collaborators")
    list_filter = ("agents_backend",)
    search_fields = ("project__name", "project__uuid", "agents_backend")
    ordering = ("project__name",)
    autocomplete_fields = ["project"]

    fieldsets = ((None, {"fields": ("project", "agents_backend", "default_instructions_for_collaborators")}),)


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("uuid", "name", "project", "is_official", "agent_type", "category")
    list_filter = ("is_official", "source_type", "agent_type", "category")
    search_fields = ("name", "project__name", "project__uuid", "slug")
    ordering = ("project__name",)
    autocomplete_fields = ["project", "group", "systems", "agent_type", "category"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "project",
                    "is_official",
                    "agent_type",
                    "category",
                    "group",
                    "systems",
                    "instruction",
                    "collaboration_instructions",
                    "foundation_model",
                    "backend_foundation_models",
                    "source_type",
                )
            },
        ),
    )


@admin.register(AgentGroup)
class AgentGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    ordering = ("name",)
    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 10, "cols": 80, "class": "vLargeTextField"})},
    }
    actions = ["apply_shared_config_to_agents"]

    def apply_shared_config_to_agents(self, request, queryset):
        updated_count = 0
        for group in queryset:
            shared = group.shared_config or {}
            for agent in group.agents.all():
                changed = False
                if "backend_foundation_models" in shared and isinstance(shared["backend_foundation_models"], dict):
                    agent.backend_foundation_models = shared["backend_foundation_models"]
                    changed = True
                if "foundation_model" in shared and isinstance(shared["foundation_model"], str):
                    agent.foundation_model = shared["foundation_model"]
                    changed = True
                if "instruction" in shared and isinstance(shared["instruction"], str):
                    agent.instruction = shared["instruction"]
                    changed = True
                if "collaboration_instructions" in shared and isinstance(shared["collaboration_instructions"], str):
                    agent.collaboration_instructions = shared["collaboration_instructions"]
                    changed = True
                if "source_type" in shared and isinstance(shared["source_type"], str):
                    agent.source_type = shared["source_type"]
                    changed = True
                if changed:
                    agent.save()
                    updated_count += 1
        messages.success(request, f"Configuration applied. Agents updated: {updated_count}")

    apply_shared_config_to_agents.short_description = "Apply shared_config to agents"


@admin.register(AgentSystem)
class AgentSystemAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    ordering = ("name",)
    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 10, "cols": 80, "class": "vLargeTextField"})},
    }


@admin.register(AgentType)
class AgentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    ordering = ("name",)


@admin.register(AgentCategory)
class AgentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    ordering = ("name",)
