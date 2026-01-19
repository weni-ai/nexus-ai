import logging
import zipfile
from io import BytesIO

from django import forms
from django.contrib import admin, messages
from django.contrib.postgres.fields import ArrayField
from django.db import models

from nexus.admin_widgets import PrettyJSONWidget
from nexus.inline_agents.backends.bedrock.models import Supervisor
from nexus.inline_agents.backends.openai.models import OpenAISupervisor, SupervisorAgent
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

    skill_file = forms.FileField(
        required=False,
        widget=forms.FileInput(),
        help_text=(
            "Upload a .py file to create a Lambda function. "
            "The Lambda ARN and metadata will be stored in Version.skills."
        ),
    )

    requirements_file = forms.FileField(
        required=False,
        widget=forms.FileInput(),
        help_text=(
            "Optional: Upload a requirements.txt file with Python dependencies. "
            "Dependencies will be included in the Lambda deployment package."
        ),
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
                "fields": ("skill_file", "requirements_file"),
                "description": (
                    "Upload a .py file to create a Lambda function. "
                    "Optionally include a requirements.txt file for dependencies. "
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

        # Process skill file if one was uploaded
        skill_file = request.FILES.get("skill_file")
        requirements_file = request.FILES.get("requirements_file")
        if skill_file and obj.is_official:
            self._process_skill_file(obj, skill_file, requirements_file, request)

    def _validate_skill_files(self, skill_file, requirements_file, request) -> bool:
        """Validate uploaded skill files"""
        if not skill_file.name.endswith(".py"):
            messages.error(request, "Only .py files are allowed for skills.")
            return False

        if requirements_file and not requirements_file.name.endswith(".txt"):
            messages.error(request, "Requirements file must be a .txt file.")
            return False

        return True

    def _read_skill_file_content(self, skill_file, request):
        """Read skill file content with robust encoding handling"""
        skill_file.seek(0)
        try:
            return skill_file.read().decode("utf-8")
        except UnicodeDecodeError:
            # Try with latin-1 as fallback (handles most encodings)
            skill_file.seek(0)
            try:
                return skill_file.read().decode("latin-1")
            except UnicodeDecodeError:
                messages.error(request, "Could not decode skill file. Please ensure it's UTF-8 encoded.")
                return None

    def _detect_tool_class(self, file_content: str):
        """Detect if code uses Tool class from weni and return class name"""
        import ast
        import re

        uses_tool_class = False
        tool_class_name = None

        try:
            # Check if imports Tool from weni
            if "from weni import Tool" in file_content or "from weni.tool import Tool" in file_content:
                uses_tool_class = True

                # Try to find the Tool class definition
                tree = ast.parse(file_content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # Check if class inherits from Tool
                        for base in node.bases:
                            if isinstance(base, ast.Name) and base.id == "Tool":
                                tool_class_name = node.name
                                break
                            elif isinstance(base, ast.Attribute):
                                if base.attr == "Tool":
                                    tool_class_name = node.name
                                    break

                # If no class found, try regex fallback
                if not tool_class_name:
                    match = re.search(r"class\s+(\w+)\s*\([^)]*Tool", file_content)
                    if match:
                        tool_class_name = match.group(1)
        except (SyntaxError, Exception) as e:
            logger.warning(f"Could not parse Python file to detect Tool class: {e}")

        return uses_tool_class, tool_class_name

    def _create_skill_zip(self, file_content: str, uses_tool_class: bool, tool_class_name, requirements_file):
        """Create ZIP file with skill code and return buffer and entrypoint"""
        zip_buffer = BytesIO()
        module_name = "main"

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if uses_tool_class and tool_class_name:
                # Create wrapper lambda_function.py for Tool class
                wrapper_code = self._create_tool_wrapper(module_name, tool_class_name)
                zip_file.writestr("lambda_function.py", wrapper_code)
                # Include original file as main.py
                zip_file.writestr("main.py", file_content.encode("utf-8"))
                entrypoint = "lambda_function.lambda_handler"
            else:
                # Use file directly as lambda_function.py
                zip_file.writestr("lambda_function.py", file_content.encode("utf-8"))
                entrypoint = "lambda_function.lambda_handler"

            # Include requirements.txt if provided
            if requirements_file:
                requirements_file.seek(0)
                requirements_content = requirements_file.read()
                zip_file.writestr("requirements.txt", requirements_content)

        zip_buffer.seek(0)
        return zip_buffer, entrypoint

    def _process_skill_file(self, agent, skill_file, requirements_file, request):
        """Process uploaded skill file and create Lambda function"""
        from nexus.usecases.inline_agents.tools import ToolsUseCase

        if not self._validate_skill_files(skill_file, requirements_file, request):
            return

        # Ensure agent has a Version
        if not agent.current_version:
            agent.versions.create(skills=[], display_skills=[])

        # Extract skill name from filename
        skill_slug = skill_file.name.replace(".py", "")
        skill_name = skill_slug.replace("_", " ").title()

        # Read file content
        file_content = self._read_skill_file_content(skill_file, request)
        if file_content is None:
            return

        # Detect if code uses Tool class
        uses_tool_class, tool_class_name = self._detect_tool_class(file_content)

        # Create zip with appropriate structure
        zip_buffer, entrypoint = self._create_skill_zip(
            file_content, uses_tool_class, tool_class_name, requirements_file
        )

        # Create tool metadata
        agent_tool = {
            "key": skill_slug,
            "name": skill_name,
            "slug": skill_slug,
            "description": f"Skill: {skill_name}",
            "parameters": [],
            "source": {
                "entrypoint": entrypoint,
            },
        }

        files_dict = {f"{agent.slug}:{skill_slug}": zip_buffer}

        # Process tool
        tools_usecase = ToolsUseCase()
        project = agent.project

        try:
            tools_usecase.handle_tools(
                agent=agent,
                project=project,
                agent_tools=[agent_tool],
                files=files_dict,
                project_uuid=str(project.uuid),
            )
            success_msg = f"Successfully processed skill file '{skill_file.name}'. Lambda function created."
            if uses_tool_class:
                success_msg += f" Detected Tool class '{tool_class_name}' and created wrapper."
            messages.success(request, success_msg)
        except Exception as e:
            logger.error(f"Error processing skill file for agent {agent.slug}: {e}", exc_info=True)
            messages.error(
                request,
                f"Error processing skill file: {str(e)}. Please check the logs for details.",
            )

    def _create_tool_wrapper(self, module_name: str, class_name: str) -> str:
        """Create a lambda_handler wrapper for Tool class"""
        return f'''import json
import os
import sys
from types import MappingProxyType

# Add current directory to path to import main module
sys.path.insert(0, os.path.dirname(__file__))

try:
    from weni.context import Context as WeniContext
    from weni.events import Event
    WENI_AVAILABLE = True
except ImportError:
    # Fallback if weni package is not available (shouldn't happen in Lambda with layer)
    WENI_AVAILABLE = False
    WeniContext = None
    Event = None

from {module_name} import {class_name}


def lambda_handler(event, context):
    """
    AWS Lambda handler wrapper for {class_name} Tool class.

    Converts Lambda event payload to weni Context and calls Tool(context).
    Tool.__new__ returns (result, format, events) tuple.
    """
    try:
        # Parse event (can be dict or JSON string)
        if isinstance(event, str):
            event = json.loads(event)

        # Extract parameters from event
        parameters = {{}}
        if "parameters" in event:
            for param in event.get("parameters", []):
                if isinstance(param, dict) and "name" in param and "value" in param:
                    parameters[param["name"]] = param["value"]

        # Extract session attributes
        session_attrs = event.get("sessionAttributes", {{}})

        # Parse JSON strings in session attributes
        credentials = {{}}
        globals_data = {{}}
        contact = {{}}
        project = {{}}

        if isinstance(session_attrs, dict):
            if "credentials" in session_attrs:
                try:
                    creds_str = session_attrs["credentials"]
                    credentials = json.loads(creds_str) if isinstance(creds_str, str) else creds_str
                except (json.JSONDecodeError, TypeError):
                    pass

            if "globals" in session_attrs:
                try:
                    globals_str = session_attrs["globals"]
                    globals_data = json.loads(globals_str) if isinstance(globals_str, str) else globals_str
                except (json.JSONDecodeError, TypeError):
                    pass

            if "contact" in session_attrs:
                try:
                    contact_str = session_attrs["contact"]
                    contact = json.loads(contact_str) if isinstance(contact_str, str) else contact_str
                except (json.JSONDecodeError, TypeError):
                    pass

            if "project" in session_attrs:
                try:
                    project_str = session_attrs["project"]
                    project = json.loads(project_str) if isinstance(project_str, str) else project_str
                except (json.JSONDecodeError, TypeError):
                    pass

        # Create Context object
        if WENI_AVAILABLE and WeniContext:
            # Use real weni Context if available
            context_obj = WeniContext(
                credentials=credentials,
                parameters=parameters,
                globals=globals_data,
                contact=contact,
                project=project
            )
        else:
            # Fallback: create simple Context-like object
            class SimpleContext:
                def __init__(self, credentials, parameters, globals_data, contact, project):
                    # Try to use MappingProxyType for immutability (like weni Context)
                    try:
                        self.credentials = MappingProxyType(credentials)
                        self.parameters = MappingProxyType(parameters)
                        self.globals = MappingProxyType(globals_data)
                        self.contact = MappingProxyType(contact)
                        self.project = MappingProxyType(project)
                    except (TypeError, AttributeError):
                        # Fallback to regular dicts if MappingProxyType fails
                        self.credentials = credentials
                        self.parameters = parameters
                        self.globals = globals_data
                        self.contact = contact
                        self.project = project
            context_obj = SimpleContext(credentials, parameters, globals_data, contact, project)

        # Call Tool class - Tool.__new__ returns (result, format, events)
        # Note: Tool.__new__ receives context and returns tuple
        result, format_dict, events = {class_name}(context_obj)

        # Ensure result is JSON serializable
        # Convert result to dict if it's a TextResponse or other object
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        elif hasattr(result, "__dict__"):
            result = result.__dict__
        elif not isinstance(result, (dict, list, str, int, float, bool, type(None))):
            # For other types, try to convert to string representation
            result = str(result)

        # Ensure format_dict is a dict
        if not isinstance(format_dict, dict):
            format_dict = {{}} if format_dict is None else {{"format": str(format_dict)}}

        # Ensure events is a list
        if not isinstance(events, list):
            events = [] if events is None else [events]

        # Format response for Lambda (matching expected structure from adapter.py)
        # The adapter expects: result.get("response", {{}}).get("sessionAttributes", {{}}).get("events", [])
        # Or: result.get("response", {{}}).get("events", [])
        return {{
            "response": {{
                "sessionAttributes": {{
                    "events": events
                }},
                "events": events,  # Fallback location
                "functionResponse": {{
                    "responseBody": result,
                    "format": format_dict
                }}
            }}
        }}

    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_str = traceback.format_exc()

        return {{
            "response": {{
                "error": error_msg,
                "errorType": type(e).__name__,
                "traceback": traceback_str,
                "sessionAttributes": {{}},
                "events": []
            }}
        }}
'''


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


@admin.register(SupervisorAgent)
class SupervisorAgentAdmin(admin.ModelAdmin):
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
