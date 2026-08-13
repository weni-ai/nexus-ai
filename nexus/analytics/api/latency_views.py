"""API views for inline agent latency (Plan B)."""

from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.analytics.api.permissions import InlineAgentLatencyAPIPermission
from nexus.analytics.latency_queries import (
    build_summary,
    build_timeseries,
    list_outliers,
    validate_date_range,
    validate_project_uuid,
)


def _parse_latency_params(request):
    project_uuid_raw = request.query_params.get("project_uuid")
    if not project_uuid_raw:
        return None, Response({"error": "project_uuid is required"}, status=400)

    project_uuid = validate_project_uuid(project_uuid_raw)
    if not project_uuid:
        return None, Response({"error": "Invalid project_uuid"}, status=400)

    start_date_str = request.query_params.get("start_date")
    end_date_str = request.query_params.get("end_date")
    if not start_date_str or not end_date_str:
        return None, Response({"error": "start_date and end_date are required (YYYY-MM-DD)"}, status=400)

    start_date = parse_date(start_date_str)
    end_date = parse_date(end_date_str)
    if not start_date or not end_date:
        return None, Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

    err = validate_date_range(start_date, end_date)
    if err:
        return None, Response({"error": err}, status=400)

    execution_path = request.query_params.get("execution_path", "inline_agents")
    return {
        "project_uuid": project_uuid,
        "start_date": start_date,
        "end_date": end_date,
        "execution_path": execution_path,
    }, None


class _InlineAgentLatencyAPIView(APIView):
    permission_classes = [InlineAgentLatencyAPIPermission]

    def get_authenticators(self):
        from weni_commons.auth import WeniAuthentication

        return [WeniAuthentication()]


class InlineAgentLatencySummaryView(_InlineAgentLatencyAPIView):
    def get(self, request):
        params, error = _parse_latency_params(request)
        if error:
            return error
        data = build_summary(
            params["project_uuid"],
            params["start_date"],
            params["end_date"],
            execution_path=params["execution_path"],
        )
        return Response(data)


class InlineAgentLatencyTimeseriesView(_InlineAgentLatencyAPIView):
    def get(self, request):
        params, error = _parse_latency_params(request)
        if error:
            return error
        phase = request.query_params.get("phase", "total")
        series = build_timeseries(
            params["project_uuid"],
            params["start_date"],
            params["end_date"],
            execution_path=params["execution_path"],
            phase=phase,
        )
        return Response({"results": series})


class InlineAgentLatencyOutliersView(_InlineAgentLatencyAPIView):
    def get(self, request):
        params, error = _parse_latency_params(request)
        if error:
            return error
        limit_raw = request.query_params.get("limit", "50")
        try:
            limit = int(limit_raw)
        except ValueError:
            return Response({"error": "limit must be an integer"}, status=400)

        rows = list_outliers(
            params["project_uuid"],
            params["start_date"],
            params["end_date"],
            execution_path=params["execution_path"],
            limit=limit,
        )
        results = [row.to_api_dict() for row in rows]
        return Response({"results": results, "count": len(results)})
