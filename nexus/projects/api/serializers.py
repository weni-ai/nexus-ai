from rest_framework import serializers

from nexus.projects.channel_ops import get_default_channel_uuid
from nexus.projects.models import Project, ProjectGuardrailsConfig


class ProjectSerializer(serializers.ModelSerializer):
    default_channel_uuid = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["uuid", "name", "brain_on", "indexer_database", "default_channel_uuid"]
        read_only_fields = ["uuid", "name", "indexer_database", "default_channel_uuid"]

    def get_default_channel_uuid(self, obj):
        return get_default_channel_uuid(str(obj.uuid))


class ProjectMinimalSerializer(serializers.ModelSerializer):
    """Minimal project representation (name, uuid only)."""

    class Meta:
        model = Project
        fields = ["name", "uuid"]
        read_only_fields = ["name", "uuid"]


class ConversationSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    contact_urn = serializers.CharField(required=False, allow_null=True)
    contact_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    status = serializers.CharField(required=False, allow_null=True)
    resolution = serializers.IntegerField(required=False, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    channel_uuid = serializers.UUIDField(required=False, allow_null=True)
    has_chats_room = serializers.BooleanField(required=False, allow_null=True)
    csat = serializers.CharField(required=False, allow_null=True)
    nps = serializers.IntegerField(required=False, allow_null=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    topic = serializers.CharField(required=False, allow_null=True)


class GuardrailCategorySerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    blocked = serializers.BooleanField()


class GuardrailsConfigResponseSerializer(serializers.Serializer):
    categories = GuardrailCategorySerializer(many=True)
    blocking_message = serializers.CharField()
    blocking_message_is_custom = serializers.BooleanField()
    writable = serializers.BooleanField()


class GuardrailsConfigUpdateSerializer(serializers.Serializer):
    category_states = serializers.DictField(
        child=serializers.BooleanField(),
        required=False,
    )
    blocking_message = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=ProjectGuardrailsConfig.BLOCKING_MESSAGE_MAX_LENGTH,
    )
    confirm_disable = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if "category_states" not in attrs and "blocking_message" not in attrs:
            raise serializers.ValidationError("At least one of category_states or blocking_message is required.")
        return attrs
