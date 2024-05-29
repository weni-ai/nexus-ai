from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from nexus.logs.models import MessageLog
from nexus.logs.api.serializers import MessageLogSerializer
from nexus.usecases.logs.list import ListLogUsecase
from rest_framework.pagination import LimitOffsetPagination


class LogsViewset(
    ModelViewSet
):

    serializer_class = MessageLogSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "contentbase_uuid"
    pagination_class = LimitOffsetPagination

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
