from rest_framework import serializers
from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText
)


class IntelligenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intelligence
        fields = ['name', 'uuid', 'content_bases_count', 'description']


class ContentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = ['title', 'uuid']


class ContentBaseTextSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseText
        fields = ['text', 'uuid']