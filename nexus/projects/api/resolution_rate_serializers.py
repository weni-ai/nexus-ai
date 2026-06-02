from rest_framework import serializers


class ProjectsResolutionRateItemSerializer(serializers.Serializer):
    project_uuid = serializers.UUIDField()
    project_name = serializers.CharField()
    resolution_rate = serializers.FloatField()
    conversation_count = serializers.IntegerField(required=False)
    resolved_count = serializers.IntegerField(required=False)
    unresolved_count = serializers.IntegerField(required=False)
    human_support_count = serializers.IntegerField(required=False)
    csat = serializers.FloatField(allow_null=True, required=False)
    csat_responses_count = serializers.IntegerField(required=False)
    nps = serializers.FloatField(allow_null=True, required=False)
    nps_responses_count = serializers.IntegerField(required=False)
    manager = serializers.CharField(required=False)
    uses_components = serializers.BooleanField(required=False)
    agents_count = serializers.IntegerField(required=False)
    official_agents_count = serializers.IntegerField(required=False)


class ProjectsResolutionRateResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    start_date = serializers.CharField(allow_null=True, required=False)
    end_date = serializers.CharField(allow_null=True, required=False)
    average_resolution_rate = serializers.FloatField()
    average_csat = serializers.FloatField(allow_null=True)
    average_nps = serializers.FloatField(allow_null=True)
    results = ProjectsResolutionRateItemSerializer(many=True)
