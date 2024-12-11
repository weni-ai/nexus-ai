from rest_framework import serializers

from nexus.actions.models import (
    Flow,
    TemplateAction,
)


class FlowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flow
        fields = ['uuid', 'name', 'prompt', 'fallback', 'content_base', 'action_type', 'group', 'editable', 'flow_uuid', 'send_to_llm']


class TemplateActionSerializer(serializers.ModelSerializer):

    class Meta:
        model = TemplateAction
        fields = ['uuid', 'name', 'group', 'display_prompt', 'language', 'action_type']
