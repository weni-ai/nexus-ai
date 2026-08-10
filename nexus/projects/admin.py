import logging
from datetime import timedelta

from django.contrib import admin
from django.db.models import JSONField
from django.utils import timezone

from nexus.admin_widgets import PrettyJSONWidget
from nexus.projects.models import Project, ProjectApiToken
from nexus.usecases.projects.project_api_token import ProjectApiTokenUseCase

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
        "bedrock_ingestion_strategy",
    )
    list_filter = (
        "agents_backend",
        "bedrock_ingestion_strategy",
        "human_support",
        "rationale_switch",
        "inline_agent_switch",
        "use_components",
        "use_prompt_creation_configurations",
        "exclude_previous_thinking_steps",
        "is_live_desk_copilot",
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
                    "bedrock_ingestion_strategy",
                    "is_live_desk_copilot",
                    "manager_agent",
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
            },
        ),
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

    @admin.action(description="Generate API token for project (expires in 1 year)")
    def generate_api_token(self, request, queryset):
        from django.contrib import messages

        created = 0
        use_case = ProjectApiTokenUseCase()
        for project in queryset:
            api_token, plaintext_token = use_case.create_token(
                project=project,
                created_by=request.user,
            )
            messages.add_message(
                request,
                messages.INFO,
                (
                    f"Project {project.name}: token generated '{api_token.name}': "
                    f"{plaintext_token}. Expires in 1 year."
                ),
            )
            created += 1

        self.message_user(request, f"{created} token(s) created.")

    actions = ["generate_api_token"]


@admin.register(ProjectApiToken)
class ProjectApiTokenAdmin(admin.ModelAdmin):
    list_display = ("project", "name", "scope", "enabled", "expires_at", "last_used_at")
    list_filter = ("scope", "enabled")
    search_fields = ("project__uuid", "project__name", "name")
    readonly_fields = ("token_hash", "salt", "created_at", "last_used_at")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "project",
                    "name",
                    "scope",
                    "enabled",
                    "expires_at",
                    "created_by",
                    "token_hash",
                    "salt",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            from django.contrib import messages

            plaintext_token, salt, token_hash = ProjectApiToken.generate_token_pair()
            obj.salt = salt
            obj.token_hash = token_hash
            obj.created_by = request.user
            if not obj.expires_at:
                obj.expires_at = timezone.now() + timedelta(days=365)
            super().save_model(request, obj, form, change)
            messages.add_message(
                request,
                messages.INFO,
                (
                    f"Token gerado para '{obj.name}': {plaintext_token}. "
                    "Guarde-o com segurança; não será mostrado novamente."
                ),
            )
        else:
            super().save_model(request, obj, form, change)
