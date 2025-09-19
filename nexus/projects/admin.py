from django.contrib import admin
from django.db import models

from nexus.projects.models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "name",
        "agents_backend",
        "human_support",
        "rationale_switch",
        "inline_agent_switch",
        "use_components",
        "default_supervisor_foundation_model",
        "default_collaborators_foundation_model",
        "use_prompt_creation_configurations",
        "conversation_turns_to_include",
        "exclude_previous_thinking_steps",
        "guardrail",
    )
    list_filter = (
        "agents_backend",
        "human_support",
        "rationale_switch",
        "inline_agent_switch",
        "use_components",
        "use_prompt_creation_configurations",
        "exclude_previous_thinking_steps",
    )
    search_fields = (
        "uuid",
        "name",
        "agents_backend",
        "default_supervisor_foundation_model",
    )
    ordering = ("-created_at",)
    readonly_fields = ("name", "uuid")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "agents_backend",
                    "human_support",
                    "human_support_prompt",
                    "rationale_switch",
                    "inline_agent_switch",
                    "use_components",
                    "default_supervisor_foundation_model",
                    "default_collaborators_foundation_model",
                    "use_prompt_creation_configurations",
                    "conversation_turns_to_include",
                    "exclude_previous_thinking_steps",
                    "guardrail",
                )
            },
        ),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if form.base_fields.get("guardrail"):
            form.base_fields["guardrail"].widget.can_delete_related = False
        return form
