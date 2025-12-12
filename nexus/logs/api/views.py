import pendulum
from django.conf import settings
from django.utils.dateparse import parse_date
from rest_framework import views
from rest_framework.exceptions import ValidationError
from rest_framework.mixins import ListModelMixin
from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from nexus.agents.api.serializers import AgentMessageDetailSerializer, AgentMessageHistorySerializer
from nexus.agents.models import AgentMessage
from nexus.logs.api.serializers import (
    InlineConversationSerializer,
    MessageDetailSerializer,
    MessageFullLogSerializer,
    MessageHistorySerializer,
    MessageLogSerializer,
    RecentActivitiesSerializer,
    TagPercentageSerializer,
)
from nexus.logs.models import MessageLog, RecentActivities
from nexus.paginations import InlineConversationsCursorPagination
from nexus.projects.api.permissions import ProjectPermission
from nexus.projects.models import Project
from nexus.usecases.agents.agents import AgentUsecase
from nexus.usecases.logs.create import CreateLogUsecase
from nexus.usecases.logs.list import ListLogUsecase
from nexus.usecases.logs.retrieve import RetrieveMessageLogUseCase


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


class TagPercentageViewSet(ListModelMixin, GenericViewSet):
    permission_classes = [ProjectPermission]

    def get_serializer_class(self):
        """Return serializer class for schema generation"""
        if getattr(self, "swagger_fake_view", False):
            from rest_framework import serializers

            return serializers.Serializer  # Use base serializer for schema generation
        return None

    def list(self, request, *args, **kwargs):
        project_uuid = self.kwargs.get("project_uuid")

        started_day = self.request.query_params.get("started_day", pendulum.now().subtract(months=1).to_date_string())
        ended_day = self.request.query_params.get("ended_day", pendulum.now().to_date_string())
        started_day = parse_date(started_day)
        ended_day = parse_date(ended_day)
        if not started_day or not ended_day:
            return Response({"error": "Invalid date format for started_day or ended_day"}, status=400)

        service_available = settings.SUPERVISOR_SERVICE_AVAILABLE
        service_available_projects = settings.SUPERVISOR_SERVICE_AVAILABLE_PROJECTS
        if not service_available and project_uuid not in service_available_projects:
            return Response([], status=200)

        source = request.query_params.get("source", "router")

        base_query = (
            MessageLog.objects.select_related("message")
            .filter(
                created_at__date__gte=started_day,
                created_at__date__lte=ended_day,
                reflection_data__tag__isnull=False,
                source=source,
                project__uuid=str(project_uuid),
            )
            .exclude(message__status="F")
        )

        if not base_query.exists():
            return Response([], status=200)

        tag_counts = {}

        action_count = base_query.filter(reflection_data__tag="action_started").count()
        tag_counts["action_count"] = action_count

        status_logs_base = base_query.exclude(reflection_data__tag="action_started")

        tag_counts["succeed_count"] = status_logs_base.filter(message__response_status_cache="S").count()

        tag_counts["failed_count"] = status_logs_base.filter(message__response_status_cache="F").count()

        total_logs = sum(tag_counts.values())
        if total_logs == 0:
            return Response([], status=200)

        action_percentage = (tag_counts["action_count"] / total_logs) * 100
        succeed_percentage = (tag_counts["succeed_count"] / total_logs) * 100
        failed_percentage = (tag_counts["failed_count"] / total_logs) * 100

        data = {
            "action_percentage": action_percentage,
            "succeed_percentage": succeed_percentage,
            "failed_percentage": failed_percentage,
        }

        serializer = TagPercentageSerializer(data)
        return Response(serializer.data)


class MessageHistoryViewset(ListModelMixin, GenericViewSet):
    pagination_class = CustomPageNumberPagination
    serializer_class = MessageHistorySerializer
    permission_classes = [ProjectPermission]

    def get_queryset(self):
        project_uuid = self.kwargs.get("project_uuid")

        params = {
            "project__uuid": project_uuid,
        }

        started_day = self.request.query_params.get("started_day", pendulum.now().subtract(months=1).to_date_string())
        ended_day = self.request.query_params.get("ended_day", pendulum.now().to_date_string())

        started_day = parse_date(started_day)
        ended_day = parse_date(ended_day)
        if not started_day or not ended_day:
            raise ValidationError({"error": "Invalid date format for started_day or ended_day"})

        service_available = settings.SUPERVISOR_SERVICE_AVAILABLE
        service_available_projects = settings.SUPERVISOR_SERVICE_AVAILABLE_PROJECTS
        if not service_available and project_uuid not in service_available_projects:
            return MessageLog.objects.none()

        params["created_at__date__gte"] = started_day
        params["created_at__date__lte"] = ended_day

        tag_param = self.request.query_params.get("tag")
        text_param = self.request.query_params.get("text")

        source = self.request.query_params.get("source", "router")
        params["source"] = source

        project = Project.objects.get(uuid=project_uuid)

        try:
            _ = project.team

            if text_param:
                params["user_text__icontains"] = text_param

            return AgentMessage.objects.filter(**params).order_by("-created_at")
        except Exception:
            if tag_param and tag_param == "action_started":
                params["reflection_data__tag"] = tag_param

            if text_param:
                params["message__text__icontains"] = text_param

            queryset = MessageLog.objects.filter(**params).exclude(reflection_data__isnull=True)

            if tag_param and tag_param != "action_started":
                status = {
                    "success": "S",
                    "failed": "F",
                }
                status_value = status.get(tag_param)
                if status_value:
                    queryset = queryset.filter(message__response_status_cache=status_value).exclude(
                        reflection_data__tag="action_started"
                    )

            return queryset.select_related("message").order_by("-created_at")

    def get_serializer_class(self):
        queryset = self.get_queryset()
        model = queryset.model
        serializers_map = {MessageLog: MessageHistorySerializer, AgentMessage: AgentMessageHistorySerializer}
        return serializers_map.get(model, self.serializer_class)


class LogsViewset(ReadOnlyModelViewSet):
    serializer_class = MessageLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = LimitOffsetPagination
    lookup_url_kwarg = "log_id"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MessageLog.objects.none()  # pragma: no cover

        params = {}

        use_case = ListLogUsecase()
        project_uuid = self.kwargs.pop("project_uuid")

        contact_urn = self.request.query_params.get("contact_urn")

        created_at_gte = self.request.query_params.get("created_at__gte")
        created_at_lte = self.request.query_params.get("created_at__lte")

        order_by = self.request.query_params.get("order_by", "desc")

        if contact_urn:
            params.update({"message__contact_urn": contact_urn})

        if created_at_gte:
            params.update({"created_at__gte": created_at_gte})

        if created_at_lte:
            params.update({"created_at__lte": created_at_lte})

        return use_case.list_logs_by_project(project_uuid=project_uuid, order_by=order_by, **params)

    def retrieve(self, request, *args, **kwargs):
        import logging

        logging.getLogger(__name__).debug("Logs retrieve kwargs", extra={"kwargs": kwargs})
        self.serializer_class = MessageFullLogSerializer
        return super().retrieve(request, *args, **kwargs)


ACTION_MODEL_GROUPS = {
    "Action": ["Flow"],
    "Customization": ["ContentBaseAgent", "ContentBaseInstruction"],
    "Content": ["ContentBase", "ContentBaseFile", "ContentBaseLink", "ContentBaseText"],
    "Config": ["LLM", "Project"],
}


class RecentActivitiesViewset(ListModelMixin, GenericViewSet):
    serializer_class = RecentActivitiesSerializer
    permission_classes = [IsAuthenticated, ProjectPermission]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RecentActivities.objects.none()  # pragma: no cover

        project = self.kwargs.get("project_uuid")

        filter_params = {"project__uuid": project}

        start_date_str = settings.RECENT_ACTIVITIES_START_DATE
        if start_date_str:
            start_date = pendulum.parse(start_date_str)
            filter_params["created_at__gte"] = start_date

        filtered_action_models = [model for models in ACTION_MODEL_GROUPS.values() for model in models]
        filter_params["action_model__in"] = filtered_action_models

        model_group = self.request.query_params.get("model_group")
        if model_group:
            models_in_group = ACTION_MODEL_GROUPS.get(model_group, [])
            filter_params["action_model__in"] = models_in_group

        queryset = (
            RecentActivities.objects.filter(**filter_params)
            .select_related("created_by")
            .order_by("-created_at")
            .exclude(action_details__isnull=True)
        )

        return queryset


class MessageDetailViewSet(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid, log_id):
        try:
            project = Project.objects.get(uuid=project_uuid)
            _ = project.team
            message_log = AgentUsecase().get_agent_message_by_id(log_id)
            return Response(AgentMessageDetailSerializer(message_log).data)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)
        except AttributeError:
            message_log = RetrieveMessageLogUseCase().get_by_id(log_id)
            message = message_log.message
            return Response(MessageDetailSerializer(message).data)

    def patch(self, request, project_uuid, log_id):
        data = request.data
        try:
            project = Project.objects.get(uuid=project_uuid)
            _ = project.team
            # TODO: update AgentMessage object
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)
        except AttributeError:
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
                response_data.update({key: getattr(usecase.log, key)})
            return Response(response_data)


class ConversationContextViewset(ListModelMixin, GenericViewSet):
    permission_classes = [ProjectPermission]

    def get_serializer_class(self):
        """Return serializer class for schema generation"""
        if getattr(self, "swagger_fake_view", False):
            from .serializers import AgentMessageDetailSerializer

            return AgentMessageDetailSerializer
        return None

    def list(self, request, *args, **kwargs):
        project_uuid = self.kwargs.get("project_uuid")
        log_id = self.request.query_params.get("log_id")
        number_of_messages = self.request.query_params.get("number_of_messages", 5)

        try:
            project = Project.objects.get(uuid=project_uuid)
            _ = project.team
            usecase = AgentUsecase()
            messages = usecase.list_last_logs(log_id=log_id, message_count=int(number_of_messages))
            serializer = AgentMessageDetailSerializer(messages, many=True)
            return Response(serializer.data)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)
        except AttributeError:
            usecase = ListLogUsecase()
            logs = usecase.list_last_logs(log_id=log_id, message_count=int(number_of_messages))
            messages = [log.message for log in logs]
            serializer = MessageDetailSerializer(messages, many=True)

            return Response(serializer.data)


class InlineConversationsViewset(ListModelMixin, GenericViewSet):
    serializer_class = InlineConversationSerializer
    pagination_class = InlineConversationsCursorPagination
    permission_classes = [IsAuthenticated, ProjectPermission]

    def list(self, request, *args, **kwargs):
        project_uuid = self.kwargs.get("project_uuid")

        start_date = request.query_params.get("start")
        end_date = request.query_params.get("end")
        contact_urn = request.query_params.get("contact_urn")

        if not all([start_date, contact_urn]):
            return Response({"error": "Missing required parameters"}, status=400)

        try:
            start = pendulum.parse(start_date)

            if end_date:
                end = pendulum.parse(end_date)
            else:
                # If no end_date provided, use start_date + 1 day
                end = start.add(days=1)

        except ValueError:
            return Response({"error": "Invalid datetime format"}, status=400)

        usecase = ListLogUsecase()
        messages = usecase.list_last_inline_messages(
            project_uuid=project_uuid, contact_urn=contact_urn, start=start, end=end
        )

        page = self.paginate_queryset(messages)
        if page is not None:
            # Reordenar os resultados dentro da página
            page = sorted(page, key=lambda x: x.created_at)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # Reordenar os resultados se não houver paginação
        messages = sorted(messages, key=lambda x: x.created_at)
        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)
