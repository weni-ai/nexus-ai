from rest_framework import serializers

from nexus.actions.models import (
    Flow
)


class FlowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flow
        fields = ['uuid', 'name', 'prompt', 'fallback', 'content_base']
