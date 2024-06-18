from prometheus_client import generate_latest

from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.views import APIView

from django.http import HttpResponse

from nexus.logs.models import MessageLog
from nexus.logs.api.serializers import MessageLogSerializer, MessageFullLogSerializer
from nexus.usecases.logs.list import ListLogUsecase
from nexus.logs.healthcheck import check_service_health


class LogsViewset(
    ReadOnlyModelViewSet
):

    serializer_class = MessageLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LimitOffsetPagination
    lookup_url_kwarg = "log_id"

    def get_queryset(self):

        if getattr(self, "swagger_fake_view", False):
            return MessageLog.objects.none()  # pragma: no cover

        params = {}

        use_case = ListLogUsecase()
        project_uuid = self.kwargs.pop('project_uuid')

        contact_urn = self.request.query_params.get('contact_urn')

        created_at_gte = self.request.query_params.get('created_at__gte')
        created_at_lte = self.request.query_params.get('created_at__lte')

        order_by = self.request.query_params.get('order_by', 'desc')

        if contact_urn:
            params.update({"message__contact_urn": contact_urn})

        if created_at_gte:
            params.update({"created_at__gte": created_at_gte})

        if created_at_lte:
            params.update({"created_at__lte": created_at_lte})

        return use_case.list_logs_by_project(
            project_uuid=project_uuid,
            order_by=order_by,
            **params
        )

    def retrieve(self, request, *args, **kwargs):
        print(kwargs)
        self.serializer_class = MessageFullLogSerializer
        return super().retrieve(request, *args, **kwargs)


class HealthCheckViewset(APIView):

    def get(self, request, *args, **kwargs):
        check_service_health()
        return HttpResponse(generate_latest(), content_type='text/plain')
