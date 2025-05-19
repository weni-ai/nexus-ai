from django.conf import settings
from rest_framework import views
from rest_framework.response import Response

from nexus.projects.api.permissions import ProjectPermission
from nexus.task_managers.tasks import generate_flows_report


class ReportView(views.APIView):
    permission_classes = [ProjectPermission]
    def get(self, request):
        return Response({
            "emails": settings.REPORT_RECIPIENT_EMAILS
        })

    def post(self, request):
        auth_token = request.data.get('auth_token')
        generate_flows_report.delay(auth_token)
        return Response({})
