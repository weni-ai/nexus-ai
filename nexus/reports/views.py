from django.conf import settings
from rest_framework import views
from rest_framework.response import Response

from nexus.projects.api.permissions import ProjectPermission
from nexus.task_managers.tasks import generate_flows_report


class ReportView(views.APIView):
    permission_classes = [ProjectPermission]

    def get(self, request):
        return Response({"emails": settings.REPORT_RECIPIENT_EMAILS})

    def post(self, request):
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        auth_token = request.data.get("auth_token")
        generate_flows_report.delay(auth_token, start_date, end_date)
        return Response({})
