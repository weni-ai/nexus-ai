from rest_framework import serializers


class ProjectApiTokenCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=False, max_length=255, trim_whitespace=True)
    scope = serializers.CharField(required=False, allow_blank=False, max_length=64, trim_whitespace=True)


class ProjectApiTokenCreateResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    token = serializers.CharField()
    scope = serializers.CharField()
    enabled = serializers.BooleanField()
    expires_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
