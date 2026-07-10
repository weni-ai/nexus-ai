from rest_framework import serializers

MAX_SHORT_TEXT_LENGTH = 255
MAX_TYPE_LENGTH = 255
MAX_CHANGE_TYPE_LENGTH = 255
MAX_IMPROVEMENT_TEXT_LENGTH = 500
MAX_DESCRIPTION_LENGTH = 5_000
MAX_SUGGESTED_CHANGE_LENGTH = 2_000
MAX_AFFECTED_INSTRUCTIONS = 50
MAX_AFFECTED_CONVERSATIONS = 50


class AffectedInstructionSerializer(serializers.Serializer):
    instruction_id = serializers.IntegerField()
    change_type = serializers.CharField(max_length=MAX_CHANGE_TYPE_LENGTH)
    was_changed = serializers.BooleanField()


class ImprovementItemSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    text = serializers.CharField(max_length=MAX_IMPROVEMENT_TEXT_LENGTH)
    type = serializers.CharField(max_length=MAX_TYPE_LENGTH)
    description = serializers.CharField(max_length=MAX_DESCRIPTION_LENGTH)
    suggested_change = serializers.CharField(max_length=MAX_SUGGESTED_CHANGE_LENGTH)
    affected_instructions = serializers.ListField(
        child=AffectedInstructionSerializer(),
        max_length=MAX_AFFECTED_INSTRUCTIONS,
    )


class AffectedConversationSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    contact_urn = serializers.CharField(max_length=MAX_SHORT_TEXT_LENGTH)
    contact_name = serializers.CharField(max_length=MAX_SHORT_TEXT_LENGTH)
    started_at = serializers.DateTimeField()


class OpenSupportTicketRequestSerializer(serializers.Serializer):
    improvement_item = ImprovementItemSerializer()
    affected_conversations = serializers.ListField(
        child=AffectedConversationSerializer(),
        max_length=MAX_AFFECTED_CONVERSATIONS,
    )
    project_uuid = serializers.UUIDField()
    user_email = serializers.EmailField(max_length=MAX_SHORT_TEXT_LENGTH)

    def validate(self, attrs):
        url_project_uuid = self.context.get("project_uuid")
        body_project_uuid = attrs.get("project_uuid")

        if url_project_uuid and str(body_project_uuid) != str(url_project_uuid):
            raise serializers.ValidationError(
                {"project_uuid": "Must match the project_uuid in the URL."}
            )

        return attrs
