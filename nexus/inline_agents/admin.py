from django.contrib import admin
from nexus.inline_agents.models import Guardrail


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
