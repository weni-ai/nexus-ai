import logging

from django.contrib import admin, messages
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.urls import reverse
from django.utils.html import format_html

from nexus.admin_widgets import ArrayJSONWidget, PrettyJSONWidget
from nexus.inline_agents.backends.bedrock.models import Supervisor
from nexus.inline_agents.backends.openai.models import ManagerAgent, OpenAISupervisor
from nexus.inline_agents.models import (
    MCP,
    Agent,
    AgentCategory,
    AgentGroup,
    AgentGroupModal,
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
    """Inline to show MCPs for an Agent (read-only, for viewing only)"""

    model = MCP
    extra = 0
    fields = ("name", "system", "description", "order", "is_active", "view_link")
    readonly_fields = ("name", "system", "description", "order", "is_active", "view_link")
    can_delete = False
    show_change_link = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("system").order_by("system__slug", "order", "name")

    def view_link(self, obj):
        """Link to view MCP in MCP admin"""
        if obj.pk:
            url = reverse("admin:inline_agents_mcp_change", args=[obj.pk])
            return format_html('<a href="{}" target="_blank">View MCP</a>', url)
        return "-"

    view_link.short_description = "View"


class VersionInline(admin.TabularInline):
    """Inline to manage Versions of an Agent"""

    model = Version
    extra = 0
    fields = ("created_on", "skills", "display_skills")
    readonly_fields = ("created_on", "skills", "display_skills")
    formfield_overrides = {
        ArrayField: {"widget": ArrayJSONWidget(attrs={"rows": 10, "cols": 80, "class": "vLargeTextField"})},
    }
    can_delete = False
    show_change_link = True

    def get_queryset(self, request):
        """Order by creation date (most recent first)"""
        qs = super().get_queryset(request)
        return qs.order_by("-created_on")


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    """Admin interface for Version model - shows skills and display_skills"""

    list_display = ("agent", "created_on")
    list_filter = ("created_on",)
    search_fields = ("agent__name", "agent__slug")
    readonly_fields = ("created_on", "skills", "display_skills")
    ordering = ("-created_on",)
    autocomplete_fields = ["agent"]

    formfield_overrides = {
        ArrayField: {"widget": ArrayJSONWidget(attrs={"rows": 10, "cols": 80, "class": "vLargeTextField"})},
    }

    fieldsets = (
        (None, {"fields": ("agent", "created_on")}),
        ("Skills", {"fields": ("skills", "display_skills")}),
    )


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("uuid", "name", "project", "is_official", "agent_type", "category")
    list_filter = ("is_official", "source_type", "agent_type", "category")
    search_fields = ("name", "project__name", "project__uuid", "slug")
    ordering = ("project__name",)
    autocomplete_fields = ["project", "group", "systems", "agent_type", "category", "mcps"]
    inlines = [VersionInline]
    readonly_fields = ("mcps_list",)

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
            "MCPs",
            {
                "fields": ("mcps", "mcps_list"),
                "description": "Select MCPs to associate with this agent. MCPs can be shared across multiple agents.",
            },
        ),
    )

    readonly_fields = ("constants", "mcps_list")

    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 10, "cols": 80, "class": "vLargeTextField"})},
    }

    def save_model(self, request, obj, form, change):
        if change:
            try:
                original = Agent.objects.get(pk=obj.pk)
                obj._old_group = original.group
            except Agent.DoesNotExist:
                obj._old_group = None
        else:
            obj._old_group = None

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        obj = form.instance
        # Sync current group
        if obj.group:
            obj.group.update_mcps_from_agents()

        # Sync old group if it existed and is different
        if hasattr(obj, "_old_group") and obj._old_group and obj._old_group != obj.group:
            obj._old_group.update_mcps_from_agents()

    def mcps_list(self, obj):
        """Display MCPs associated with this agent with links to view them"""
        if not obj.pk:
            return "Save the agent first to see associated MCPs"

        mcps = obj.mcps.all().select_related("system").order_by("system__slug", "order", "name")

        if not mcps.exists():
            mcp_admin_url = reverse("admin:inline_agents_mcp_changelist")
            return format_html(
                '<p>No MCPs found for this agent. <a href="{}" target="_blank">Create MCP</a></p>',
                mcp_admin_url,
            )

        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += '<thead><tr><th style="padding: 8px; border: 1px solid #ddd;">Name</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">System</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">Description</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">Status</th>'
        html += '<th style="padding: 8px; border: 1px solid #ddd;">Actions</th></tr></thead><tbody>'

        for mcp in mcps:
            view_url = reverse("admin:inline_agents_mcp_change", args=[mcp.pk])
            status = "Active" if mcp.is_active else "Inactive"
            status_color = "green" if mcp.is_active else "gray"
            description = (
                mcp.description[:50] + "..."
                if mcp.description and len(mcp.description) > 50
                else (mcp.description or "-")
            )

            html += "<tr>"
            html += f'<td style="padding: 8px; border: 1px solid #ddd;"><strong>{mcp.name}</strong></td>'
            html += f'<td style="padding: 8px; border: 1px solid #ddd;">{mcp.system.name if mcp.system else "-"}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #ddd;">{description}</td>'
            html += (
                f'<td style="padding: 8px; border: 1px solid #ddd;"><span style="color: {status_color};">'
                f"{status}</span></td>"
            )
            html += (
                f'<td style="padding: 8px; border: 1px solid #ddd;"><a href="{view_url}" target="_blank">'
                f"View MCP</a></td>"
            )
            html += "</tr>"

        html += "</tbody></table>"

        mcp_admin_url = reverse("admin:inline_agents_mcp_changelist")
        html += f'<p style="margin-top: 10px;"><a href="{mcp_admin_url}" target="_blank">+ Create new MCP</a></p>'

        return format_html(html)

    mcps_list.short_description = "Associated MCPs"


class AgentGroupModalInline(admin.StackedInline):
    model = AgentGroupModal
    extra = 0
    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 10, "cols": 80, "class": "vLargeTextField"})},
    }


class AgentInline(admin.TabularInline):
    model = Agent
    extra = 0
    fields = ("name", "uuid", "is_official")
    readonly_fields = ("name", "uuid", "is_official")
    can_delete = False
    show_change_link = True


class AgentGroupMCPInline(admin.TabularInline):
    model = AgentGroup.mcps.through
    extra = 0
    verbose_name = "Associated MCP"
    verbose_name_plural = "Associated MCPs"
    can_delete = False
    max_num = 0

    fields = ("get_name", "get_system", "get_description", "get_status", "view_link")
    readonly_fields = ("get_name", "get_system", "get_description", "get_status", "view_link")

    def get_name(self, obj):
        return obj.mcp.name

    get_name.short_description = "Name"

    def get_system(self, obj):
        return obj.mcp.system.name if obj.mcp.system else "-"

    get_system.short_description = "System"

    def get_description(self, obj):
        return obj.mcp.description

    get_description.short_description = "Description"

    def get_status(self, obj):
        return "Active" if obj.mcp.is_active else "Inactive"

    get_status.short_description = "Status"

    def view_link(self, obj):
        if obj.mcp.pk:
            url = reverse("admin:inline_agents_mcp_change", args=[obj.mcp.pk])
            return format_html('<a href="{}" target="_blank">View MCP</a>', url)
        return "-"

    view_link.short_description = "Actions"


@admin.register(AgentGroup)
class AgentGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    inlines = [AgentGroupModalInline, AgentInline, AgentGroupMCPInline]
    search_fields = ("name", "slug")
    ordering = ("name",)
    exclude = ("mcps",)
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
    list_display = ("name", "slug", "logo")
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
    fields = ("name", "label", "type", "options", "default_value", "order", "is_required")
    formfield_overrides = {
        models.JSONField: {"widget": PrettyJSONWidget(attrs={"rows": 5, "cols": 60, "class": "vLargeTextField"})},
    }


class MCPCredentialTemplateInline(admin.TabularInline):
    model = MCPCredentialTemplate
    extra = 0
    fields = ("name", "label", "placeholder", "is_confidential", "order")


@admin.register(MCP)
class MCPAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "system", "order", "is_active")
    list_filter = ("is_active", "system")
    search_fields = ("name", "slug", "description", "system__name", "system__slug")
    ordering = ("system", "order", "name")
    autocomplete_fields = ["system"]
    inlines = [MCPConfigOptionInline, MCPCredentialTemplateInline]

    fieldsets = ((None, {"fields": ("name", "slug", "description", "system", "order", "is_active")}),)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("system")

    def save_model(self, request, obj, form, change):
        """Save model and trigger cache invalidation for all associated agents."""
        super().save_model(request, obj, form, change)

        # Fire cache invalidation event for team update for all agents using this MCP
        try:
            from nexus.events import notify_async

            # Get all projects from agents that use this MCP
            projects = set()
            for agent in obj.agents.all():
                if agent.project:
                    projects.add(agent.project.uuid)

            for project_uuid in projects:
                notify_async(
                    event="cache_invalidation:team",
                    project_uuid=str(project_uuid),
                )
            logger.info(f"[Admin] Triggered cache invalidation for MCP {obj.name} (affecting {len(projects)} projects)")
        except Exception as e:
            logger.warning(f"[Admin] Failed to trigger cache invalidation for MCP: {e}")

    def delete_model(self, request, obj):
        """Delete model and trigger cache invalidation for all associated agents."""
        # Get all projects from agents that use this MCP before deletion
        projects = set()
        for agent in obj.agents.all():
            if agent.project:
                projects.add(agent.project.uuid)

        super().delete_model(request, obj)

        # Fire cache invalidation event for team update
        if projects:
            try:
                from nexus.events import notify_async

                for project_uuid in projects:
                    notify_async(
                        event="cache_invalidation:team",
                        project_uuid=str(project_uuid),
                    )
                logger.info(
                    f"[Admin] Triggered cache invalidation after MCP deletion (affecting {len(projects)} projects)"
                )
            except Exception as e:
                logger.warning(f"[Admin] Failed to trigger cache invalidation after MCP deletion: {e}")


@admin.register(ManagerAgent)
class ManagerAgentAdmin(admin.ModelAdmin):
    list_display = ("name", "foundation_model", "created_on")
    list_filter = ("foundation_model",)
    search_fields = ("name", "instruction")
    readonly_fields = ("created_on",)
    ordering = ("-created_on",)

    fieldsets = (
        (
            "Base Configuration",
            {
                "fields": (
                    "name",
                    "default",
                    "public",
                    "release_date",
                    "base_prompt",
                    "model_vendor",
                    "foundation_model",
                    "api_key",
                    "api_base",
                    "api_version",
                    "max_tokens",
                    "collaborator_max_tokens",
                    "tools",
                    "knowledge_bases",
                    "parallel_tool_calls",
                    "model_has_reasoning",
                    "reasoning_effort",
                    "reasoning_summary",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Human Support",
            {
                "fields": ("human_support_prompt", "human_support_tools"),
                "classes": ("collapse",),
            },
        ),
        (
            "Audio Orchestration",
            {
                "fields": ("audio_orchestration_max_tokens", "audio_orchestration_collaborator_max_tokens"),
                "classes": ("collapse",),
            },
        ),
        (
            "Components",
            {
                "fields": (
                    "header_components_prompt",
                    "footer_components_prompt",
                    "formatter_agent_prompt",
                    "formatter_agent_foundation_model",
                    "formatter_agent_model_has_reasoning",
                    "formatter_agent_reasoning_effort",
                    "formatter_agent_reasoning_summary",
                    "formatter_agent_send_only_assistant_message",
                    "formatter_agent_tools_descriptions",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Collaborators",
            {
                "fields": (
                    "collaborators_foundation_model",
                    "override_collaborators_foundation_model",
                    "default_instructions_for_collaborators",
                ),
                "classes": ("collapse",),
            },
        ),
    )
