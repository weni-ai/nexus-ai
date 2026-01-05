import logging
import zipfile
from io import BytesIO

from django import forms
from django.contrib import admin, messages
from django.contrib.postgres.fields import ArrayField
from django.db import models

from nexus.admin_widgets import PrettyJSONWidget
from nexus.inline_agents.backends.bedrock.models import Supervisor
from nexus.inline_agents.backends.openai.models import OpenAISupervisor
from nexus.inline_agents.models import (
    MCP,
    Agent,
    AgentCategory,
    AgentGroup,
    AgentSystem,
    AgentType,
    Guardrail,
    InlineAgentsConfiguration,
    MCPConfigOption,
    MCPCredentialTemplate,
    Version,
)

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


class MCPInline(admin.TabularInline):
    """Inline to show and manage MCPs for an Agent"""

    model = MCP
    extra = 1
    fields = ("name", "system", "description", "order", "is_active")
    autocomplete_fields = ["system"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("system").order_by("system__slug", "order", "name")


class VersionInline(admin.TabularInline):
    """Inline to manage Versions of an Agent"""

    model = Version
    extra = 0
    fields = ("created_on", "skills", "display_skills")
    readonly_fields = ("created_on",)
    formfield_overrides = {
        ArrayField: {"widget": PrettyJSONWidget(attrs={"rows": 10, "cols": 80, "class": "vLargeTextField"})},
    }

    def get_queryset(self, request):
        """Order by creation date (most recent first)"""
        qs = super().get_queryset(request)
        return qs.order_by("-created_on")


class AgentAdminForm(forms.ModelForm):
    """Custom form to handle skill file uploads"""

    skill_files = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"multiple": True}),
        help_text="Upload .py files for skills. Lambda functions will be created automatically.",
    )

    class Meta:
        model = Agent
        fields = [
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
            "variant",
            "capabilities",
            "policies",
            "tooling",
            "catalog",
        ]


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    form = AgentAdminForm
    list_display = ("uuid", "name", "project", "is_official", "agent_type", "category")
    list_filter = ("is_official", "source_type", "agent_type", "category")
    search_fields = ("name", "project__name", "project__uuid", "slug")
    ordering = ("project__name",)
    autocomplete_fields = ["project", "group", "systems", "agent_type", "category"]
    inlines = [MCPInline, VersionInline]

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
        (
            "Skills",
            {
                "fields": ("skill_files",),
                "description": (
                    "Upload .py files to create Lambda functions. "
                    "The Lambda ARN and metadata will be stored in Version.skills. "
                    "The actual .py code is stored in AWS Lambda, not in the database."
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Variant & Capabilities",
            {
                "fields": (
                    "variant",
                    "capabilities",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Regionalization Policies",
            {
                "fields": ("policies",),
                "classes": ("collapse",),
            },
        ),
        (
            "Tooling",
            {
                "fields": ("tooling",),
                "classes": ("collapse",),
            },
        ),
        (
            "Catalog Integration",
            {
                "fields": ("catalog",),
                "classes": ("collapse",),
            },
        ),
    )

    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 10, "cols": 80, "class": "vLargeTextField"})},
    }

    def save_model(self, request, obj, form, change):
        """Override save to create empty Version and process skill files"""
        # Save the agent first (this will create empty Version if needed via Agent.save())
        super().save_model(request, obj, form, change)

        # Process skill files if any were uploaded
        skill_files = request.FILES.getlist("skill_files")
        if skill_files and obj.is_official:
            self._process_skill_files(obj, skill_files, request)

    def _process_skill_files(self, agent, skill_files, request):
        """Process uploaded skill files and create Lambda functions"""
        from nexus.usecases.inline_agents.tools import ToolsUseCase

        tools_usecase = ToolsUseCase()
        project = agent.project

        # Ensure agent has a Version
        if not agent.current_version:
            agent.versions.create(skills=[], display_skills=[])

        agent_tools = []
        files_dict = {}

        for skill_file in skill_files:
            if not skill_file.name.endswith(".py"):
                continue

            # Extract skill name from filename
            skill_slug = skill_file.name.replace(".py", "")
            skill_name = skill_slug.replace("_", " ").title()

            # Read file content
            skill_file.seek(0)
            file_content = skill_file.read()

            # Create zip from .py file (Lambda expects zip)
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.writestr("lambda_function.py", file_content)
            zip_buffer.seek(0)

            # Create tool metadata
            agent_tool = {
                "key": skill_slug,
                "name": skill_name,
                "slug": skill_slug,
                "description": f"Skill: {skill_name}",
                "parameters": [],
                "source": {
                    "entrypoint": "lambda_function.lambda_handler",
                },
            }

            agent_tools.append(agent_tool)
            files_dict[f"{agent.slug}:{skill_slug}"] = zip_buffer

        # Process tools if any were uploaded
        if agent_tools:
            try:
                tools_usecase.handle_tools(
                    agent=agent,
                    project=project,
                    agent_tools=agent_tools,
                    files=files_dict,
                    project_uuid=str(project.uuid),
                )
                messages.success(
                    request,
                    f"Successfully processed {len(agent_tools)} skill file(s). Lambda functions created.",
                )
            except Exception as e:
                logger.error(f"Error processing skill files for agent {agent.slug}: {e}", exc_info=True)
                messages.error(
                    request,
                    f"Error processing skill files: {str(e)}. Please check the logs for details.",
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


class MCPConfigOptionInline(admin.TabularInline):
    model = MCPConfigOption
    extra = 0
    fields = ("name", "label", "type", "options", "order", "is_required")
    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 5, "cols": 60, "class": "vLargeTextField"})},
    }


class MCPCredentialTemplateInline(admin.TabularInline):
    model = MCPCredentialTemplate
    extra = 0
    fields = ("name", "label", "placeholder", "is_confidential", "order")


@admin.register(MCP)
class MCPAdmin(admin.ModelAdmin):
    list_display = ("name", "agent", "system", "order", "is_active")
    list_filter = ("is_active", "system", "agent")
    search_fields = ("name", "description", "agent__name", "agent__slug", "system__name", "system__slug")
    ordering = ("agent", "system", "order", "name")
    autocomplete_fields = ["agent", "system"]
    inlines = [MCPConfigOptionInline, MCPCredentialTemplateInline]

    fieldsets = ((None, {"fields": ("name", "description", "agent", "system", "order", "is_active")}),)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("agent", "system")

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
