import pendulum

from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination

from rest_framework.mixins import ListModelMixin
from rest_framework.viewsets import GenericViewSet
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from nexus.logs.models import MessageLog, RecentActivities
from nexus.logs.api.serializers import (
    MessageLogSerializer,
    MessageFullLogSerializer,
    RecentActivitiesSerializer,
    MessageHistorySerializer,
    TagPercentageSerializer
)
from nexus.usecases.logs.list import ListLogUsecase

from nexus.projects.permissions import has_project_permission

from django.conf import settings
from django.db.models import Count, Case, When, IntegerField
from django.utils.dateparse import parse_date


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


class TagPercentageViewSet(
    ListModelMixin,
    GenericViewSet
):

    def list(self, request, *args, **kwargs):
        user = self.request.user
        project_uuid = self.kwargs.get('project_uuid')

        has_project_permission(user, project_uuid, 'GET')

        started_day = request.query_params.get('started_day')
        if not started_day:
            return Response({"error": "started_day parameter is required"}, status=400)

        started_day = parse_date(started_day)
        if not started_day:
            return Response({"error": "Invalid date format for started_day"}, status=400)

        source = request.query_params.get('source', 'router')
        message_logs = MessageLog.objects.filter(
            created_at__date=started_day,
            reflection_data__tag__isnull=False,
            source=source,
            project__uuid=str(project_uuid)
        )

        if not message_logs.exists():
            return Response({"error": "No logs found for the given started_day"}, status=404)

        tag_counts = message_logs.aggregate(
            action_count=Count(Case(When(reflection_data__tag='action_started', then=1), output_field=IntegerField())),
            succeed_count=Count(Case(When(reflection_data__tag='success', then=1), output_field=IntegerField())),
            failed_count=Count(Case(When(reflection_data__tag='failed', then=1), output_field=IntegerField()))
        )

        total_logs = sum(tag_counts.values())
        if total_logs == 0:
            return Response({"error": "No logs found for the given started_day"}, status=404)

        action_percentage = (tag_counts['action_count'] / total_logs) * 100
        succeed_percentage = (tag_counts['succeed_count'] / total_logs) * 100
        failed_percentage = (tag_counts['failed_count'] / total_logs) * 100

        data = {
            "action_percentage": action_percentage,
            "succeed_percentage": succeed_percentage,
            "failed_percentage": failed_percentage
        }

        serializer = TagPercentageSerializer(data)
        return Response(serializer.data)


class MessageHistoryViewset(
    ListModelMixin,
    GenericViewSet
):
    pagination_class = CustomPageNumberPagination
    serializer_class = MessageHistorySerializer

    def get_queryset(self):

        user = self.request.user
        project_uuid = self.kwargs.get('project_uuid')

        has_project_permission(user, project_uuid, 'GET')

        params = {
            "project__uuid": project_uuid,
        }

        started_day_param = self.request.query_params.get('started_day')
        tag_param = self.request.query_params.get('tag')
        text_param = self.request.query_params.get('text')

        source = self.request.query_params.get('source', 'router')
        params["source"] = source

        if started_day_param:
            params["created_at__date"] = started_day_param

        if tag_param:
            params["reflection_data__tag"] = tag_param

        if text_param:
            params["message__text__icontains"] = text_param

        return MessageLog.objects.filter(
            **params
        ).exclude(
            reflection_data__isnull=True
        ).select_related(
            'message'
        ).order_by(
            '-created_at'
        )


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
