from rest_framework import serializers


class FlowsDbCohortReconcileRequestSerializer(serializers.Serializer):
    """Body for POST ``/api/v2/<project_uuid>/flows-db-cohort`` (nexus-ai proxy)."""

    flows_api_token = serializers.CharField(write_only=True, trim_whitespace=False)
    date_start = serializers.CharField()
    date_end = serializers.CharField()
    apply_terminal_cohort_filter = serializers.BooleanField(default=True)
    key = serializers.CharField(required=False, default="conversation_classification")
    authorization_prefix = serializers.CharField(required=False, default="Token")
    flows_page_limit = serializers.IntegerField(required=False, default=10_000, min_value=1, max_value=10_000)
    flows_offset_start = serializers.IntegerField(required=False, default=0, min_value=0)
    flows_max_pages = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=1, max_value=200
    )
    mismatch_sample_limit = serializers.IntegerField(required=False, default=20, min_value=0, max_value=500)
    uuid_sample_limit = serializers.IntegerField(required=False, default=20, min_value=0, max_value=500)

    def validate(self, attrs):
        from django.conf import settings as django_settings

        from nexus.projects.services.flows_db_cohort_service import (
            parse_api_utc,
            validate_reconcile_date_range,
        )

        max_days = int(getattr(django_settings, "FLOWS_DB_COHORT_MAX_RANGE_DAYS", 31))

        try:
            start_bound = parse_api_utc(str(attrs["date_start"]).strip())
        except ValueError as e:
            raise serializers.ValidationError({"date_start": str(e)}) from e

        end_raw = str(attrs["date_end"]).strip()
        try:
            end_bound = parse_api_utc(end_raw)
        except ValueError as e:
            raise serializers.ValidationError({"date_end": str(e)}) from e

        try:
            validate_reconcile_date_range(start_bound, end_bound, max_days)
        except ValueError as e:
            raise serializers.ValidationError({"date_end": str(e)}) from e

        token = str(attrs.get("flows_api_token", "")).strip()
        if not token:
            raise serializers.ValidationError({"flows_api_token": "This field may not be blank."})
        attrs["flows_api_token"] = token
        attrs["date_start"] = str(attrs["date_start"]).strip()
        attrs["date_end"] = end_raw
        return attrs
