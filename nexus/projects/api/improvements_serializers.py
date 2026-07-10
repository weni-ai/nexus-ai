from rest_framework import serializers


class AffectedInstructionSerializer(serializers.Serializer):
    instruction_id = serializers.IntegerField()
    change_type = serializers.CharField()
    was_changed = serializers.BooleanField()


class ImprovementItemSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    text = serializers.CharField()
    type = serializers.CharField()
    description = serializers.CharField()
    suggested_change = serializers.CharField()
    affected_instructions = AffectedInstructionSerializer(many=True)


class AffectedConversationSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    contact_urn = serializers.CharField()
    contact_name = serializers.CharField()
    started_at = serializers.DateTimeField()


class OpenSupportTicketRequestSerializer(serializers.Serializer):
    improvement_item = ImprovementItemSerializer()
    affected_conversations = AffectedConversationSerializer(many=True)
    project_uuid = serializers.UUIDField()
    user_email = serializers.EmailField()

    def validate(self, attrs):
        url_project_uuid = self.context.get("project_uuid")
        body_project_uuid = attrs.get("project_uuid")

        if url_project_uuid and str(body_project_uuid) != str(url_project_uuid):
            raise serializers.ValidationError(
                {"project_uuid": "Must match the project_uuid in the URL."}
            )

        return attrs
