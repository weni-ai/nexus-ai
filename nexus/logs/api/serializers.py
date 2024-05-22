from rest_framework import serializers
from nexus.logs.models import MessageLog


class MessageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageLog
        fields = [
            "message_text",
            "message_exception",
            "contact_urn",
            "chunks",
            "prompt",
            "project",
            "content_base",
            "classification",
            "llm_model",
            "llm_response",
            "created_at",
            "metadata",
        ]

    message_text = serializers.SerializerMethodField()
    message_exception = serializers.SerializerMethodField()
    project = serializers.SerializerMethodField()
    contact_urn = serializers.SerializerMethodField()

    def get_message_text(self, obj: MessageLog) -> str:
        return obj.message.text

    def get_message_exception(self, obj: MessageLog) -> str:
        return obj.message.exception

    def get_project(self, obj: MessageLog) -> str:
        return f"{obj.project.uuid} - {obj.project.name}"

    def get_contact_urn(self, obj: MessageLog) -> str:
        return obj.message.contact_urn
