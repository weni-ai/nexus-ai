import json

from django.contrib import admin
from django.db import models
from django.forms import Textarea

from nexus.inline_agents.backends.bedrock.models import Supervisor
from nexus.inline_agents.backends.openai.models import OpenAISupervisor
from nexus.inline_agents.models import (
    Agent,
    Guardrail,
    InlineAgentsConfiguration,
)


class PrettyJSONWidget(Textarea):
    def render(self, name, value, attrs=None, renderer=None):
        if value and isinstance(value, str):
            try:
                # Parse the JSON string and then re-format it with indentation
                value_dict = json.loads(value)
                value = json.dumps(value_dict, indent=2)
            except json.JSONDecodeError:
                pass
        elif value and not isinstance(value, str):
            # If it's already a dict or list, just format it
            value = json.dumps(value, indent=2)

        # Call the parent class's render method with the formatted JSON
        return super().render(name, value, attrs, renderer)


@admin.register(Guardrail)
class GuardrailAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'version', 'created_on', 'current_version')
    list_filter = ('current_version', 'identifier')
    search_fields = ('identifier', 'changelog')
    readonly_fields = ('created_on',)
    ordering = ('-created_on',)

    fieldsets = (
        (None, {
            'fields': ('identifier', 'version', 'current_version')
        }),
        ('Content', {
            'fields': ('changelog',)
        }),
        ('Metadata', {
            'fields': ('created_on',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Supervisor)
class SupervisorAdmin(admin.ModelAdmin):
    list_display = ('name', 'foundation_model', 'created_on')
    list_filter = ('foundation_model',)
    search_fields = ('name', 'instruction')
    readonly_fields = ('created_on',)
    ordering = ('-created_on',)

    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget(attrs={'rows': 20, 'cols': 80, 'class': 'vLargeTextField'})},
    }

    fieldsets = (
        (None, {
            'fields': ('name', 'foundation_model', 'instruction')
        }),
        ('Configuration', {
            'fields': ('prompt_override_configuration', 'action_groups', 'knowledge_bases')
        }),
        ('Human Support', {
            'fields': ('human_support_prompt', 'human_support_action_groups'),
            'classes': ('collapse',)
        }),
        ('Components', {
            'fields': ('components_prompt', 'components_human_support_prompt'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_on',),
            'classes': ('collapse',)
        }),
    )


@admin.register(OpenAISupervisor)
class OpenAISupervisorAdmin(admin.ModelAdmin):
    list_display = ('name', 'foundation_model', 'created_on')
    list_filter = ('foundation_model',)
    search_fields = ('name', 'instruction')
    readonly_fields = ('created_on',)
    ordering = ('-created_on',)

    formfield_overrides = {
        models.JSONField: {'widget': PrettyJSONWidget(attrs={'rows': 20, 'cols': 80, 'class': 'vLargeTextField'})},
    }

    fieldsets = (
        (None, {
            'fields': ('name', 'foundation_model', 'instruction', 'default_instructions_for_collaborators', 'max_tokens')
        }),
        ('Configuration', {
            'fields': ('prompt_override_configuration', 'action_groups', 'knowledge_bases'),
            'classes': ('collapse',)
        }),
        ('Human Support', {
            'fields': ('human_support_prompt', 'human_support_action_groups'),
            'classes': ('collapse',)
        }),
        ('Components', {
            'fields': ('components_prompt', 'components_human_support_prompt', 'components_instructions_up_prompt'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_on',),
            'classes': ('collapse',)
        }),
    )


@admin.register(InlineAgentsConfiguration)
class InlineAgentsConfigurationAdmin(admin.ModelAdmin):
    list_display = ('project', 'agents_backend', 'default_instructions_for_collaborators')
    list_filter = ('agents_backend',)
    search_fields = ('project__name', 'project__uuid', 'agents_backend')
    ordering = ('project__name',)
    autocomplete_fields = ['project']

    fieldsets = (
        (None, {
            'fields': ('project', 'agents_backend', 'default_instructions_for_collaborators', 'text_orchestration_exclusive_tools', 'audio_orchestration_exclusive_tools')
        }),
    )


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'name', 'project', 'is_official')
    list_filter = ('is_official', 'source_type')
    search_fields = ('name', 'project__name', 'project__uuid', 'slug')
    ordering = ('project__name',)
    autocomplete_fields = ['project']

    fieldsets = (
        (None, {
            'fields': ('name', 'project', 'is_official', 'instruction', 'collaboration_instructions', 'foundation_model', 'backend_foundation_models', 'source_type', 'audio_orchestration', 'text_orchestration')
        }),
    )
