import json

from django import forms
from django.contrib import admin, messages
from django.db import models
from django.forms import Textarea

from nexus.inline_agents.backends.bedrock.models import Supervisor
from nexus.inline_agents.models import Guardrail


class PrettyJSONWidget(Textarea):
    def render(self, name, value, attrs=None, renderer=None):
        if value and isinstance(value, str):
            try:
                value_dict = json.loads(value)
                value = json.dumps(value_dict, indent=2)
            except json.JSONDecodeError:
                pass
        elif value and not isinstance(value, str):
            value = json.dumps(value, indent=2)

        return super().render(name, value, attrs, renderer)


@admin.register(Guardrail)
class GuardrailAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'version', 'created_on', 'current_version')
    list_filter = ('current_version', 'identifier')
    search_fields = ('identifier', 'changelog')
    readonly_fields = ('created_on',)
    ordering = ('-created_on',)

    fieldsets = (
        (None, {'fields': ('identifier', 'version', 'current_version')}),
        ('Content', {'fields': ('changelog',)}),
        ('Metadata', {'fields': ('created_on',), 'classes': ('collapse',)}),
    )


class SupervisorForm(forms.ModelForm):
    new_action_group = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 80}),
        help_text='Add a new action group. It will be added to both action_groups and human_support_action_groups.',
    )
    default_action_groups_list = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 80}),
        help_text='Action groups used by default in the supervisor.',
    )

    human_support_action_groups_list = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 80}),
        help_text='Action groups used by supervisor with human support activated.',
    )

    class Meta:
        model = Supervisor
        fields = [
            'name',
            'foundation_model',
            'instruction',
            'prompt_override_configuration',
            'action_groups',
            'knowledge_bases',
            'new_action_group',
            'human_support_prompt',
            'human_support_action_groups',
            'components_prompt',
            'components_human_support_prompt',
            'default_action_groups_list',
            'human_support_action_groups_list',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields[
                'default_action_groups_list'
            ].initial = self.instance.action_groups_list
            self.fields[
                'human_support_action_groups_list'
            ].initial = self.instance.human_support_action_groups_list


@admin.register(Supervisor)
class SupervisorAdmin(admin.ModelAdmin):
    form = SupervisorForm
    list_display = ('name', 'foundation_model', 'created_on')
    list_filter = ('foundation_model',)
    search_fields = ('name', 'instruction')
    readonly_fields = ('created_on',)
    ordering = ('-created_on',)

    formfield_overrides = {
        models.JSONField: {
            'widget': PrettyJSONWidget(
                attrs={'rows': 20, 'cols': 80, 'class': 'vLargeTextField'}
            )
        },
    }

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'name',
                    'foundation_model',
                )
            },
        ),
        (
            'Prompts',
            {
                'fields': (
                    'instruction',
                    'human_support_prompt',
                    'components_prompt',
                    'components_human_support_prompt',
                ),
                'classes': ('collapse',),
            },
        ),
        (
            'Action Groups',
            {
                'fields': (
                    'default_action_groups_list',
                    'human_support_action_groups_list',
                    'new_action_group',
                    'action_groups',
                    'human_support_action_groups',
                ),
                'classes': ('collapse',),
            },
        ),
        (
            'Configuration',
            {
                'fields': (
                    'prompt_override_configuration',
                    'knowledge_bases',
                )
            },
        ),
        ('Metadata', {'fields': ('created_on',), 'classes': ('collapse',)}),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['new_action_group'] = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            help_text='Add a new action group. It will be added to both action_groups and human_support_action_groups.',
        )
        form.base_fields['default_action_groups_list'] = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            help_text='Action groups used by default in the supervisor.',
            disabled=True,
        )
        form.base_fields['human_support_action_groups_list'] = forms.CharField(
            required=False,
            widget=forms.Textarea(attrs={'rows': 4, 'cols': 80}),
            help_text='Action groups used by supervisor with human support activated.',
            disabled=True,
        )
        return form

    def save_model(self, request, obj, form, change):
        new_action_group = form.cleaned_data.get('new_action_group')
        if new_action_group:
            try:
                new_action_group = json.loads(new_action_group)
                action_groups = obj.action_groups or []
                action_groups.append(new_action_group)
                obj.action_groups = action_groups

                if obj.human_support_action_groups is not None:
                    human_support_action_groups = (
                        obj.human_support_action_groups or []
                    )
                    human_support_action_groups.append(new_action_group)
                    obj.human_support_action_groups = (
                        human_support_action_groups
                    )
            except Exception as e:
                self.message_user(
                    request,
                    f'Error adding new action group: {str(e)}',
                    level=messages.ERROR,
                )

        super().save_model(request, obj, form, change)
