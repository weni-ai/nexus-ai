from rest_framework import serializers


class ResolutionRateSerializer(serializers.Serializer):
    """Serializer for average resolution rate endpoint"""
    resolution_rate = serializers.FloatField()
    unresolved_rate = serializers.FloatField()
    total_conversations = serializers.IntegerField()
    resolved_conversations = serializers.IntegerField()
    unresolved_conversations = serializers.IntegerField()
    breakdown = serializers.DictField()
    filters = serializers.DictField()


class IndividualProjectResolutionSerializer(serializers.Serializer):
    """Serializer for individual project in resolution rate list"""
    project_uuid = serializers.UUIDField()
    project_name = serializers.CharField()
    motor = serializers.CharField()
    resolution_rate = serializers.FloatField()
    total = serializers.IntegerField()
    resolved = serializers.IntegerField()
    unresolved = serializers.IntegerField()


class IndividualResolutionRateSerializer(serializers.Serializer):
    """Serializer for individual resolution rate endpoint"""
    projects = IndividualProjectResolutionSerializer(many=True)
    filters = serializers.DictField()


class UnresolvedRateSerializer(serializers.Serializer):
    """Serializer for unresolved rate endpoint"""
    unresolved_rate = serializers.FloatField()
    total_conversations = serializers.IntegerField()
    unresolved_conversations = serializers.IntegerField()
    filters = serializers.DictField()


class ProjectByMotorSerializer(serializers.Serializer):
    """Serializer for a single project in projects-by-motor response"""
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    conversation_count = serializers.IntegerField()


class MotorProjectsSerializer(serializers.Serializer):
    """Serializer for projects grouped by motor"""
    count = serializers.IntegerField()
    projects = ProjectByMotorSerializer(many=True)


class ProjectsByMotorSerializer(serializers.Serializer):
    """Serializer for projects by motor endpoint.
    
    Fields use underscores (AB_2, AB_2_5) for schema generation,
    but to_representation converts to space-separated keys ('AB 2', 'AB 2.5').
    """
    AB_2 = MotorProjectsSerializer(required=False, allow_null=True)
    AB_2_5 = MotorProjectsSerializer(required=False, allow_null=True)

    def to_representation(self, instance):
        """Custom representation to handle dynamic keys"""
        ret = {}
        # Convert underscore keys to space-separated keys in output
        if 'AB 2' in instance:
            ret['AB 2'] = MotorProjectsSerializer(instance['AB 2']).data
        elif 'AB_2' in instance:
            ret['AB 2'] = MotorProjectsSerializer(instance['AB_2']).data
        
        if 'AB 2.5' in instance:
            ret['AB 2.5'] = MotorProjectsSerializer(instance['AB 2.5']).data
        elif 'AB_2_5' in instance:
            ret['AB 2.5'] = MotorProjectsSerializer(instance['AB_2_5']).data
        return ret

