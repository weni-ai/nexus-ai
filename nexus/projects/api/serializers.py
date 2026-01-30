from rest_framework import serializers

from nexus.projects.models import Project


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["uuid", "name", "brain_on", "indexer_database"]
        read_only_fields = ["uuid", "name", "indexer_database"]


class ConversationClassificationSerializer(serializers.Serializer):
    topic = serializers.CharField(required=False, allow_null=True)
    subtopic = serializers.CharField(required=False, allow_null=True)
    confidence = serializers.FloatField(required=False, allow_null=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    updated_at = serializers.DateTimeField(required=False, allow_null=True)


class ConversationSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    contact_urn = serializers.CharField(required=False, allow_null=True)
    contact_name = serializers.CharField(required=False, allow_null=True)
    status = serializers.CharField(required=False, allow_null=True)
    resolution = serializers.IntegerField(required=False, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    channel_uuid = serializers.UUIDField(required=False, allow_null=True)
    has_chats_room = serializers.BooleanField(required=False, allow_null=True)
    csat = serializers.CharField(required=False, allow_null=True)
    nps = serializers.IntegerField(required=False, allow_null=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    classification = ConversationClassificationSerializer(required=False, allow_null=True)
