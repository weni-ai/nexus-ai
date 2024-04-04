from rest_framework import serializers

from nexus.projects.models import Project


class UpdateProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['uuid', 'name', 'description', 'brain_on', 'is_router']
        read_only_fields = ['uuid', 'is_router', 'description', 'name']
