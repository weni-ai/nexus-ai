import logging
from datetime import timedelta

from django.contrib import admin
from django.db.models import JSONField
from django.utils import timezone

from nexus.admin_widgets import PrettyJSONWidget
from nexus.projects.models import Project, ProjectApiToken

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
                    "supervisor",
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

        from nexus.projects.models import ProjectApiToken

        created = 0
        for project in queryset:
            token, salt, token_hash = ProjectApiToken.generate_token_pair()
            api_token = ProjectApiToken.objects.create(
                project=project,
                name=f"Auto {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
                salt=salt,
                token_hash=token_hash,
                created_by=request.user,
                expires_at=timezone.now() + timedelta(days=365),
            )
            messages.add_message(
                request,
                messages.INFO,
                f"Project {project.name}: token generated '{api_token.name}': {token}. Expires in 1 year.",
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
            from nexus.projects.models import ProjectApiToken

            token, salt, token_hash = ProjectApiToken.generate_token_pair()
            obj.salt = salt
            obj.token_hash = token_hash
            obj.created_by = request.user
            if not obj.expires_at:
                obj.expires_at = timezone.now() + timedelta(days=365)
            super().save_model(request, obj, form, change)
            from django.contrib import messages

            messages.add_message(
                request,
                messages.INFO,
                f"Token gerado para '{obj.name}': {token}. Guarde-o com segurança; não será mostrado novamente.",
            )
        else:
            super().save_model(request, obj, form, change)
