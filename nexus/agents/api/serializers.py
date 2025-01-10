from rest_framework import serializers

from nexus.agents.models import ActiveAgent


class ActiveAgentSerializer(serializers.Serializer):

    class Meta:
        model = ActiveAgent
        fields = ['uuid', 'agent', 'team', 'is_official']


class ActiveAgentTeamSerializer(serializers.Serializer):

    class Meta:
        model = ActiveAgent
        fields = ['uuid', 'agent', 'team', 'is_official']
