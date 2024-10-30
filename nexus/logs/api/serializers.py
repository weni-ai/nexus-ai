from rest_framework import serializers
from nexus.logs.models import MessageLog, RecentActivities


class TagPercentageSerializer(serializers.Serializer):

    class Meta:
        model = MessageLog
        fields = [
            "action_percentage",
            "succeed_percentage",
            "failed_percentage",
        ]

    action_percentage = serializers.FloatField()
    succeed_percentage = serializers.FloatField()
    failed_percentage = serializers.FloatField()


class MessageHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageLog
        fields = [
            "id",
            "created_at",
            "message_text",
            "tag",
            "classification"
        ]

    message_text = serializers.SerializerMethodField()
    tag = serializers.SerializerMethodField()

    def get_message_text(self, obj: MessageLog) -> str:
        return obj.message.text

    def get_tag(self, obj: MessageLog) -> str:
        return obj.reflection_data.get("tag", "failed")


class MessageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageLog
        fields = [
            "id",
            "message_text",
            "message_exception",
            "contact_urn",
            "classification",
            "llm_model",
            "llm_response",
            "created_at",
        ]

    message_text = serializers.SerializerMethodField()
    message_exception = serializers.SerializerMethodField()
    contact_urn = serializers.SerializerMethodField()

    def get_message_text(self, obj: MessageLog) -> str:
        return obj.message.text

    def get_message_exception(self, obj: MessageLog) -> str:
        return obj.message.exception

    def get_contact_urn(self, obj: MessageLog) -> str:
        return obj.message.contact_urn


class MessageFullLogSerializer(MessageLogSerializer):
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

    def get_project(self, obj: MessageLog) -> str:
        return f"{obj.project.uuid} - {obj.project.name}"


class RecentActivitiesSerializer(serializers.ModelSerializer):

    class Meta:
        model = RecentActivities
        fields = [
            "uuid",
            "model_group",
            "action_model",
            "created_at",
            "action_details",
            "action_type",
            "project",
            "created_by",
        ]

    created_by = serializers.SerializerMethodField()
    model_group = serializers.SerializerMethodField()

    def get_created_by(self, obj: RecentActivities) -> str:
        return obj.created_by.email

    def get_model_group(self, obj: RecentActivities) -> str:

        ACTION_MODEL_GROUPS = {
            "Flow": "Action",
            "ContentBaseAgent": "Customization",
            "ContentBaseInstruction": "Customization",
            "ContentBase": "Content",
            "ContentBaseFile": "Content",
            "ContentBaseLink": "Content",
            "ContentBaseText": "Content",
            "LLM": "Config",
        }
        return ACTION_MODEL_GROUPS.get(obj.action_model, "")
