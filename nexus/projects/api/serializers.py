from rest_framework import serializers

from nexus.projects.models import Project


class UpdateProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['uuid', 'name', 'brain_on']
        read_only_fields = ['uuid', 'name']
