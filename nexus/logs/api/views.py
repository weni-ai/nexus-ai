import pendulum

from rest_framework import views
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
from nexus.usecases.logs.retrieve import RetrieveMessageLogUseCase
from nexus.usecases.logs.create import CreateLogUsecase

from nexus.projects.permissions import has_project_permission

from django.conf import settings
from django.db.models import Count, Case, When, IntegerField
from django.utils.dateparse import parse_date

from nexus.logs.api.serializers import MessageDetailSerializer
from nexus.projects.api.permissions import ProjectPermission


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
        def count_status(logs, tag):
            logs = [log for log in logs if log.message.response_status == tag]
            return len(logs)

        user = self.request.user
        project_uuid = self.kwargs.get('project_uuid')

        has_project_permission(user, project_uuid, 'GET')

        started_day = self.request.query_params.get(
            'started_day',
            pendulum.now().subtract(months=1).to_date_string()
        )
        ended_day = self.request.query_params.get(
            'ended_day',
            pendulum.now().to_date_string()
        )
        started_day = parse_date(started_day)
        ended_day = parse_date(ended_day)
        if not started_day or not ended_day:
            return Response({"error": "Invalid date format for started_day or ended_day"}, status=400)

        source = request.query_params.get('source', 'router')
        message_logs = MessageLog.objects.filter(
            created_at__date__gte=started_day,
            created_at__date__lte=ended_day,
            reflection_data__tag__isnull=False,
            source=source,
            project__uuid=str(project_uuid)
        )
        message_logs = message_logs.exclude(message__status="F")

        if not message_logs.exists():
            return Response({"error": "No logs found for the given date range"}, status=404)

        tag_counts = message_logs.aggregate(action_count=Count(Case(When(reflection_data__tag='action_started', then=1), output_field=IntegerField())))

        status_message_logs = message_logs.exclude(reflection_data__tag="action_started")

        tag_counts.update({
            "succeed_count": count_status(status_message_logs, "S"),
            "failed_count": count_status(status_message_logs, "F"),
        })

        total_logs = sum(tag_counts.values())
        if total_logs == 0:
            return Response({"error": "No logs found for the given date range"}, status=404)

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

        started_day = self.request.query_params.get(
            'started_day',
            pendulum.now().subtract(months=1).to_date_string()
        )
        ended_day = self.request.query_params.get(
            'ended_day',
            pendulum.now().to_date_string()
        )

        started_day = parse_date(started_day)
        ended_day = parse_date(ended_day)
        if not started_day or not ended_day:
            return Response({"error": "Invalid date format for started_day or ended_day"}, status=400)

        params["created_at__date__gte"] = started_day
        params["created_at__date__lte"] = ended_day

        tag_param = self.request.query_params.get('tag')
        text_param = self.request.query_params.get('text')

        source = self.request.query_params.get('source', 'router')
        params["source"] = source

        if tag_param and tag_param == "action_started":
            params["reflection_data__tag"] = tag_param

        if text_param:
            params["message__text__icontains"] = text_param

        logs = MessageLog.objects.filter(
            **params
        ).exclude(
            reflection_data__isnull=True
        ).select_related(
            'message'
        ).order_by(
            '-created_at'
        )

        if tag_param and tag_param != "action_started":
            status = {
                "success": "S",
                "failed": "F",
            }
            logs = [log for log in logs if log.message.response_status == status.get(tag_param) and log.reflection_data.get("tag") != "action_started"]

        return logs


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
    "Config": ["LLM", "Project"],
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

        model_group = self.request.query_params.get('model_group')
        if model_group:
            models_in_group = ACTION_MODEL_GROUPS.get(model_group, [])
            filter_params['action_model__in'] = models_in_group

        queryset = RecentActivities.objects.filter(**filter_params).select_related('created_by').order_by('-created_at').exclude(action_details__isnull=True)

        return queryset


class MessageDetailViewSet(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid, log_id):
        message_log = RetrieveMessageLogUseCase().get_by_id(log_id)
        message = message_log.message
        return Response(MessageDetailSerializer(message).data)

    def patch(self, request, project_uuid, log_id):
        data = request.data
        usecase = CreateLogUsecase()
        message_log = RetrieveMessageLogUseCase().get_by_id(log_id)

        usecase.message = message_log.message
        usecase.log = message_log

        serializer = MessageDetailSerializer(usecase.message, data=data, partial=True)
        serializer.is_valid()

        usecase.update_log_field(**data)
        keys = list(data.keys())
        response_data = {}

        for key in keys:
            response_data.update(
                {
                    key: getattr(usecase.log, key)
                }
            )
        return Response(response_data)


class ConversationContextViewset(
    ListModelMixin,
    GenericViewSet
):

    serializer_class = MessageDetailSerializer

    def list(self, request, *args, **kwargs):
        user = self.request.user
        project_uuid = self.kwargs.get('project_uuid')
        log_id = self.request.query_params.get('log_id')
        number_of_messages = self.request.query_params.get('number_of_messages', 5)

        has_project_permission(user, project_uuid, 'GET')

        usecase = ListLogUsecase()
        logs = usecase.list_last_logs(
            log_id=log_id,
            message_count=int(number_of_messages)
        )
        messages = [log.message for log in logs]
        serializer = MessageDetailSerializer(messages, many=True)

        return Response(serializer.data)
