from rest_framework import serializers

from nexus.projects.models import Project


class FeatureFlagsQueryParamsSerializer(serializers.Serializer):
    """Query params for listing active feature flags for a project."""

    project_uuid = serializers.UUIDField(required=True)

    def validate(self, attrs):
        project_uuid = attrs.get("project_uuid")
        project = Project.objects.filter(uuid=project_uuid).first()
        if not project:
            raise serializers.ValidationError({"project_uuid": "Project not found."})
        attrs["project"] = project
        return attrs
