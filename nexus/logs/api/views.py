import pendulum

from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination

from rest_framework.mixins import ListModelMixin
from rest_framework.viewsets import GenericViewSet
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from nexus.logs.models import MessageLog, RecentActivities
from nexus.logs.api.serializers import MessageLogSerializer, MessageFullLogSerializer, RecentActivitiesSerializer
from nexus.usecases.logs.list import ListLogUsecase

from nexus.projects.permissions import has_project_permission

from django.conf import settings


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })


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


ACTION_MODEL_GROUPS = {
    "Action": ["Flow"],
    "Customization": ["ContentBaseAgent", "ContentBaseInstruction"],
    "Content": ["ContentBase", "ContentBaseFile", "ContentBaseLink", "ContentBaseText"],
    "Config": ["LLM"],
}


class RecentActivitiesViewset(
    ListModelMixin,
    GenericViewSet
):
    serializer_class = RecentActivitiesSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RecentActivities.objects.none()  # pragma: no cover

        user = self.request.user
        project = self.kwargs.get('project_uuid')
        has_project_permission(user, project, 'GET')

        filter_params = {
            'project': project
        }

        start_date_str = settings.RECENT_ACTIVITIES_START_DATE
        if start_date_str:
            start_date = pendulum.parse(start_date_str)
            filter_params['created_at__gte'] = start_date

        filtered_action_models = [model for models in ACTION_MODEL_GROUPS.values() for model in models]
        filter_params['action_model__in'] = filtered_action_models

        queryset = RecentActivities.objects.filter(**filter_params).select_related('created_by').order_by('-created_at').exclude(action_details__isnull=True)

        return queryset
