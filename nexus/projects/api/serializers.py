from rest_framework import serializers

from nexus.projects.models import Project


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['uuid', 'name', 'brain_on', 'indexer_database']
        read_only_fields = ['uuid', 'name', 'indexer_database']
