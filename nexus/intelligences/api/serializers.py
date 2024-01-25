from rest_framework import serializers
from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile
)


class IntelligenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intelligence
        fields = ['name', 'uuid', 'content_bases_count', 'description']


class ContentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = ['uuid', 'title', 'description']


class ContentBaseTextSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseText
        fields = ['text', 'uuid']


class ContentBaseFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseFile
        fields = ["file", "extension_file", "uuid", "created_file_name"]
