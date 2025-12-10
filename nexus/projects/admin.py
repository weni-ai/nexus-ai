import logging

from django.contrib import admin
from django.db.models import JSONField

from nexus.admin_widgets import PrettyJSONWidget
from nexus.projects.models import Project

logger = logging.getLogger(__name__)


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

    formfield_overrides = {
        JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 20, "cols": 80, "class": "vLargeTextField"})},
    }

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
        (
            "Formatter Agent Configurations",
            {
                "fields": (
                    "default_formatter_foundation_model",
                    "formatter_instructions",
                    "formatter_reasoning_effort",
                    "formatter_reasoning_summary",
                    "formatter_send_only_assistant_message",
                    "formatter_tools_descriptions",
                )
            }
        )
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if form.base_fields.get("guardrail"):
            form.base_fields["guardrail"].widget.can_delete_related = False
        return form

    def save_model(self, request, obj, form, change):
        """Save model and trigger cache invalidation."""
        super().save_model(request, obj, form, change)

        # Fire cache invalidation event for project update
        try:
            from nexus.events import notify_async

            notify_async(
                event="cache_invalidation:project",
                project=obj,
            )
            logger.info(f"[Admin] Triggered cache invalidation for project {obj.uuid}")
        except Exception as e:
            logger.warning(f"[Admin] Failed to trigger cache invalidation for project {obj.uuid}: {e}")
