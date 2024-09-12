from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination

from rest_framework.mixins import ListModelMixin
from rest_framework.viewsets import GenericViewSet
from rest_framework.pagination import CursorPagination

from nexus.logs.models import MessageLog, RecentActivities
from nexus.logs.api.serializers import MessageLogSerializer, MessageFullLogSerializer, RecentActivitiesSerializer
from nexus.usecases.logs.list import ListLogUsecase

from nexus.projects.permissions import has_project_permission


class CustomCursorPagination(CursorPagination):
    page_size_query_param = 'page_size'
    page_size = 20

    def paginate_queryset(self, queryset, request, view=None):
        self.ordering = view.get_ordering()
        return super().paginate_queryset(queryset, request, view)


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


class RecentActivitiesViewset(
    ListModelMixin,
    GenericViewSet
):
    serializer_class = RecentActivitiesSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomCursorPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RecentActivities.objects.none()  # pragma: no cover

        user = self.request.user
        project = self.kwargs.get('project_uuid')
        has_project_permission(user, project, 'GET')

        return RecentActivities.objects.filter(project=self.kwargs.get('project_uuid'))

    def get_ordering(self):
        return ["-created_at"]
