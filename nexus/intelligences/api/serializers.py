from rest_framework import serializers
from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    ContentBaseLogs
)
from nexus.task_managers.models import ContentBaseFileTaskManager


class IntelligenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Intelligence
        fields = ['name', 'uuid', 'content_bases_count', 'description', 'is_router']


class ContentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = ['uuid', 'title', 'description', 'language', 'is_router']


class RouterContentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBase
        fields = '__all__'


class ContentBaseTextSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseText
        fields = ['text', 'uuid']


class ContentBaseFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseFile
        fields = ["file", "extension_file", "uuid", "created_file_name", "status", "file_name"]

    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        try:
            task_manager = obj.upload_tasks.get()
            return task_manager.status
        except Exception:
            return ContentBaseFileTaskManager.STATUS_FAIL


class ContentBaseLogsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentBaseLogs
        fields = [
            "question",
            "language",
            "texts_chunks",
            "full_prompt",
            "weni_gpt_response",
            "wenigpt_version",
            "testing",
            "feedback",
            "correct_answer",
        ]
