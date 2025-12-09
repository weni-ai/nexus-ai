from uuid import UUID

import pendulum
from django.db.models import Count, Q
from django.utils.dateparse import parse_date
from mozilla_django_oidc.contrib.drf import OIDCAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.authentication.authentication import ExternalTokenAuthentication
from nexus.intelligences.models import Conversation
from nexus.orgs import permissions as org_permissions
from nexus.projects.models import Project

from .serializers import (
    IndividualResolutionRateSerializer,
    ProjectsByMotorSerializer,
    ResolutionRateSerializer,
    UnresolvedRateSerializer,
)


class InternalCommunicationPermission(BasePermission):
    """Permission class for internal service-to-service communication or external tokens"""

    def has_permission(self, request, view):
        # Check if using external token authentication (superuser token)
        authorization_header = request.headers.get("Authorization")
        if authorization_header:
            try:
                if org_permissions.is_super_user(authorization_header):
                    return True
            except (IndexError, AttributeError):
                pass

        # Check if user has internal communication permission
        user = request.user
        if user and user.is_authenticated:
            return user.has_perm("users.can_communicate_internally")

        return False


# Motor to backend mapping
MOTOR_BACKEND_MAP = {
    "AB 2": "BedrockBackend",
    "AB 2.5": "OpenAIBackend",
}


def get_motor_from_backend(backend):
    """Helper function to get motor identifier from backend"""
    if backend == "BedrockBackend":
        return "AB 2"
    elif backend == "OpenAIBackend":
        return "AB 2.5"
    return None


def validate_and_parse_dates(start_date_str, end_date_str):
    """Validate and parse date strings, returning defaults if not provided"""
    if not start_date_str:
        start_date = pendulum.now().subtract(months=1).date()
    else:
        start_date = parse_date(start_date_str)
        if not start_date:
            return None, None, Response({"error": "Invalid start_date format. Use YYYY-MM-DD"}, status=400)

    if not end_date_str:
        end_date = pendulum.now().date()
    else:
        end_date = parse_date(end_date_str)
        if not end_date:
            return None, None, Response({"error": "Invalid end_date format. Use YYYY-MM-DD"}, status=400)

    if start_date > end_date:
        return None, None, Response({"error": "start_date must be before or equal to end_date"}, status=400)

    return start_date, end_date, None


class ResolutionRateAverageView(APIView):
    authentication_classes = [ExternalTokenAuthentication, OIDCAuthentication]
    permission_classes = [InternalCommunicationPermission]

    def get(self, request):
        # Prevent database access during schema generation
        if getattr(self, "swagger_fake_view", False):
            return Response({})
        """
        GET /api/analytics/resolution-rate/average/

        Query params:
        - project_uuid (optional): Filter by specific project UUID
        - start_date (optional, YYYY-MM-DD): Start date
        - end_date (optional, YYYY-MM-DD): End date
        - motor (optional, "AB 2" | "AB 2.5"): Filter by specific motor
        - min_conversations (optional, int): Minimum conversations to consider project
        """
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        motor = request.query_params.get("motor")
        min_conversations_str = request.query_params.get("min_conversations")
        project_uuid = request.query_params.get("project_uuid")

        # Validate and parse dates
        start_date, end_date, error_response = validate_and_parse_dates(start_date_str, end_date_str)
        if error_response:
            return error_response

        # Validate project_uuid if provided
        if project_uuid:
            try:
                UUID(project_uuid)
            except (ValueError, TypeError):
                return Response(
                    {"error": "project_uuid must be a valid UUID format"},
                    status=400,
                )

        # Validate motor if provided
        if motor and motor not in MOTOR_BACKEND_MAP:
            return Response(
                {"error": f"Invalid motor value. Must be one of: {', '.join(MOTOR_BACKEND_MAP.keys())}"},
                status=400,
            )

        # Validate min_conversations if provided
        min_conversations = None
        if min_conversations_str:
            try:
                min_conversations = int(min_conversations_str)
                if min_conversations < 0:
                    return Response(
                        {"error": "min_conversations must be a non-negative integer"},
                        status=400,
                    )
            except ValueError:
                return Response({"error": "min_conversations must be a valid integer"}, status=400)

        conversations = (
            Conversation.objects.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                resolution__in=["0", "1", "2", "3", "4"],
            )
            .exclude(resolution__isnull=True)
            .select_related("project")
        )

        if project_uuid:
            conversations = conversations.filter(project__uuid=project_uuid)

        if motor:
            backend_value = MOTOR_BACKEND_MAP[motor]
            conversations = conversations.filter(project__agents_backend=backend_value)

        project_stats = conversations.values("project__uuid").annotate(
            total_conversations=Count("uuid"),
            resolved_cnt=Count("uuid", filter=Q(resolution="0")),
            unresolved_cnt=Count("uuid", filter=Q(resolution="1")),
            in_progress_cnt=Count("uuid", filter=Q(resolution="2")),
            unclassified_cnt=Count("uuid", filter=Q(resolution="3")),
            has_chat_cnt=Count("uuid", filter=Q(resolution="4")),
        )

        if min_conversations is not None:
            project_stats = project_stats.filter(total_conversations__gte=min_conversations)

        project_rates = []
        total_resolved = 0
        total_unresolved = 0
        total_in_progress = 0
        total_unclassified = 0
        total_has_chat = 0
        total_conversations_all = 0

        for ps in project_stats:
            total_considered = (
                ps["resolved_cnt"]
                + ps["unresolved_cnt"]
                + ps["in_progress_cnt"]
                + ps["unclassified_cnt"]
                + ps["has_chat_cnt"]
            )
            if total_considered > 0:
                resolution_rate_pct = 100.0 * ps["resolved_cnt"] / total_considered
                project_rates.append(resolution_rate_pct)
                total_resolved += ps["resolved_cnt"]
                total_unresolved += ps["unresolved_cnt"]
                total_in_progress += ps["in_progress_cnt"]
                total_unclassified += ps["unclassified_cnt"]
                total_has_chat += ps["has_chat_cnt"]
                total_conversations_all += ps["total_conversations"]

        if project_rates:
            resolution_rate = sum(project_rates) / len(project_rates) / 100.0
            unresolved_rate = float(total_unresolved / total_conversations_all) if total_conversations_all > 0 else 0.0
        else:
            resolution_rate = 0.0
            unresolved_rate = 0.0
            total_conversations_all = 0

        response_data = {
            "resolution_rate": round(resolution_rate, 4),
            "unresolved_rate": round(unresolved_rate, 4),
            "total_conversations": total_conversations_all,
            "resolved_conversations": total_resolved,
            "unresolved_conversations": total_unresolved,
            "breakdown": {
                "resolved": total_resolved,
                "unresolved": total_unresolved,
                "in_progress": total_in_progress,
                "unclassified": total_unclassified,
                "has_chat_room": total_has_chat,
            },
            "filters": {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "project_uuid": project_uuid,
                "motor": motor,
                "min_conversations": min_conversations,
            },
        }

        serializer = ResolutionRateSerializer(response_data)
        return Response(serializer.data)


class ResolutionRateIndividualView(APIView):
    authentication_classes = [ExternalTokenAuthentication, OIDCAuthentication]
    permission_classes = [InternalCommunicationPermission]

    def get(self, request):
        # Prevent database access during schema generation
        if getattr(self, "swagger_fake_view", False):
            return Response({})
        """
        GET /api/analytics/resolution-rate/individual/

        Query params: Same as average endpoint, plus:
        - filter_project_uuid (optional): Filter by specific project UUID
        - filter_project_name (optional): Filter by project name (partial search, case-insensitive)
        Returns: Array of project-level metrics
        """
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        motor = request.query_params.get("motor")
        min_conversations_str = request.query_params.get("min_conversations")
        project_uuid = request.query_params.get("project_uuid")
        filter_project_uuid = request.query_params.get("filter_project_uuid")
        filter_project_name = request.query_params.get("filter_project_name")

        # Validate and parse dates
        start_date, end_date, error_response = validate_and_parse_dates(start_date_str, end_date_str)
        if error_response:
            return error_response

        # Validate motor if provided
        if motor and motor not in MOTOR_BACKEND_MAP:
            return Response(
                {"error": f"Invalid motor value. Must be one of: {', '.join(MOTOR_BACKEND_MAP.keys())}"},
                status=400,
            )

        # Validate min_conversations if provided
        min_conversations = None
        if min_conversations_str:
            try:
                min_conversations = int(min_conversations_str)
                if min_conversations < 0:
                    return Response(
                        {"error": "min_conversations must be a non-negative integer"},
                        status=400,
                    )
            except ValueError:
                return Response({"error": "min_conversations must be a valid integer"}, status=400)

        # Validate project_uuid if provided
        if project_uuid:
            try:
                UUID(project_uuid)
            except (ValueError, TypeError):
                return Response(
                    {"error": "project_uuid must be a valid UUID format"},
                    status=400,
                )

        # Build base query across all projects
        conversations = Conversation.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).select_related("project")

        # Filter by project_uuid if provided
        if project_uuid:
            conversations = conversations.filter(project__uuid=project_uuid)

        # Filter by motor if provided
        if motor:
            backend_value = MOTOR_BACKEND_MAP[motor]
            conversations = conversations.filter(project__agents_backend=backend_value)

        # Group by project and calculate metrics
        project_stats = (
            conversations.values("project__uuid", "project__name", "project__agents_backend")
            .annotate(
                total=Count("uuid"),
                resolved=Count("uuid", filter=Q(resolution="0")),
                unresolved=Count("uuid", filter=Q(resolution="1")),
            )
            .order_by("-total")
        )

        # Filter by additional project filters (UUID or name)
        if filter_project_uuid:
            try:
                # Validate UUID format
                UUID(filter_project_uuid)
                project_stats = project_stats.filter(project__uuid=filter_project_uuid)
            except (ValueError, TypeError):
                return Response(
                    {"error": "filter_project_uuid must be a valid UUID format"},
                    status=400,
                )

        if filter_project_name:
            project_stats = project_stats.filter(project__name__icontains=filter_project_name)

        # Filter by min_conversations
        if min_conversations is not None:
            project_stats = project_stats.filter(total__gte=min_conversations)

        # Build response
        projects_data = []
        for stat in project_stats:
            total = stat["total"]
            resolved = stat["resolved"]
            unresolved = stat["unresolved"]
            motor_value = get_motor_from_backend(stat["project__agents_backend"])

            resolution_rate = float(resolved / total) if total > 0 else 0.0

            projects_data.append(
                {
                    "project_uuid": stat["project__uuid"],
                    "project_name": stat["project__name"],
                    "motor": motor_value or "Unknown",
                    "resolution_rate": round(resolution_rate, 4),
                    "total": total,
                    "resolved": resolved,
                    "unresolved": unresolved,
                }
            )

        response_data = {
            "projects": projects_data,
            "filters": {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "motor": motor,
                "min_conversations": min_conversations,
                "filter_project_uuid": filter_project_uuid,
                "filter_project_name": filter_project_name,
            },
        }

        serializer = IndividualResolutionRateSerializer(response_data)
        return Response(serializer.data)


class UnresolvedRateView(APIView):
    authentication_classes = [ExternalTokenAuthentication, OIDCAuthentication]
    permission_classes = [InternalCommunicationPermission]

    def get(self, request):
        # Prevent database access during schema generation
        if getattr(self, "swagger_fake_view", False):
            return Response({})
        """
        GET /api/analytics/unresolved-rate/

        Query params:
        - project_uuid (optional): Filter by specific project UUID
        - start_date (optional, YYYY-MM-DD): Start date
        - end_date (optional, YYYY-MM-DD): End date
        - motor (optional, "AB 2" | "AB 2.5"): Filter by specific motor
        - min_conversations (optional, int): Minimum conversations to consider project
        Returns: Unresolved rate metrics
        """
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        motor = request.query_params.get("motor")
        min_conversations_str = request.query_params.get("min_conversations")
        project_uuid = request.query_params.get("project_uuid")

        # Validate and parse dates
        start_date, end_date, error_response = validate_and_parse_dates(start_date_str, end_date_str)
        if error_response:
            return error_response

        # Validate project_uuid if provided
        if project_uuid:
            try:
                UUID(project_uuid)
            except (ValueError, TypeError):
                return Response(
                    {"error": "project_uuid must be a valid UUID format"},
                    status=400,
                )

        # Validate motor if provided
        if motor and motor not in MOTOR_BACKEND_MAP:
            return Response(
                {"error": f"Invalid motor value. Must be one of: {', '.join(MOTOR_BACKEND_MAP.keys())}"},
                status=400,
            )

        # Validate min_conversations if provided
        min_conversations = None
        if min_conversations_str:
            try:
                min_conversations = int(min_conversations_str)
                if min_conversations < 0:
                    return Response(
                        {"error": "min_conversations must be a non-negative integer"},
                        status=400,
                    )
            except ValueError:
                return Response({"error": "min_conversations must be a valid integer"}, status=400)

        # Build base query (across all projects, or filtered by project_uuid)
        conversations = Conversation.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).select_related("project")

        # Filter by project_uuid if provided
        if project_uuid:
            conversations = conversations.filter(project__uuid=project_uuid)

        # Filter by motor if provided
        if motor:
            backend_value = MOTOR_BACKEND_MAP[motor]
            conversations = conversations.filter(project__agents_backend=backend_value)

        # Filter by min_conversations
        if min_conversations is not None:
            project_counts = (
                conversations.values("project__uuid").annotate(count=Count("uuid")).filter(count__gte=min_conversations)
            )
            project_uuids = [pc["project__uuid"] for pc in project_counts]
            conversations = conversations.filter(project__uuid__in=project_uuids)

        # Aggregate statistics (focus on unresolved)
        stats = conversations.aggregate(
            total=Count("uuid"),
            unresolved=Count("uuid", filter=Q(resolution="1")),
        )

        # Calculate unresolved rate
        total = stats["total"]
        unresolved = stats["unresolved"]
        unresolved_rate = float(unresolved / total) if total > 0 else 0.0

        response_data = {
            "unresolved_rate": round(unresolved_rate, 4),
            "total_conversations": total,
            "unresolved_conversations": unresolved,
            "filters": {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "project_uuid": project_uuid,
                "motor": motor,
                "min_conversations": min_conversations,
            },
        }

        serializer = UnresolvedRateSerializer(response_data)
        return Response(serializer.data)


class ProjectsByMotorView(APIView):
    authentication_classes = [ExternalTokenAuthentication, OIDCAuthentication]
    permission_classes = [InternalCommunicationPermission]

    def get(self, request):
        # Prevent database access during schema generation
        if getattr(self, "swagger_fake_view", False):
            return Response({})
        user = request.user
        if not user or not getattr(user, "is_authenticated", False):
            return Response({"detail": "Authentication credentials were not provided."}, status=401)
        """
        GET /api/analytics/projects/by-motor/

        Query params:
        - motor ("AB 2" | "AB 2.5" | "both"): Which motor to search
        - start_date (optional, YYYY-MM-DD): Filter conversations by date
        - end_date (optional, YYYY-MM-DD): Filter conversations by date
        """
        motor_param = request.query_params.get("motor", "both")
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        # Validate motor parameter
        if motor_param not in ["AB 2", "AB 2.5", "both"]:
            return Response(
                {"error": 'motor must be one of: "AB 2", "AB 2.5", "both"'},
                status=400,
            )

        # Validate and parse dates if provided
        date_filter = Q()
        if start_date_str and end_date_str:
            start_date, end_date, error_response = validate_and_parse_dates(start_date_str, end_date_str)
            if error_response:
                return error_response
            date_filter = Q(
                conversations__created_at__date__gte=start_date,
                conversations__created_at__date__lte=end_date,
            )
        elif start_date_str or end_date_str:
            # Both must be provided if either is provided
            return Response(
                {"error": "Both start_date and end_date must be provided together"},
                status=400,
            )

        results = {}

        # Get AB 2 projects (BedrockBackend)
        if motor_param in ["AB 2", "both"]:
            ab2_query = Project.objects.filter(agents_backend="BedrockBackend", is_active=True)

            if date_filter:
                ab2_projects = (
                    ab2_query.annotate(conversation_count=Count("conversations", filter=date_filter))
                    .values("uuid", "name", "conversation_count")
                    .order_by("-conversation_count")
                )
            else:
                ab2_projects = (
                    ab2_query.annotate(conversation_count=Count("conversations"))
                    .values("uuid", "name", "conversation_count")
                    .order_by("-conversation_count")
                )

            ab2_list = list(ab2_projects)
            results["AB 2"] = {"count": len(ab2_list), "projects": ab2_list}

        # Get AB 2.5 projects (OpenAIBackend)
        if motor_param in ["AB 2.5", "both"]:
            ab2_5_query = Project.objects.filter(agents_backend="OpenAIBackend", is_active=True)

            if date_filter:
                ab2_5_projects = (
                    ab2_5_query.annotate(conversation_count=Count("conversations", filter=date_filter))
                    .values("uuid", "name", "conversation_count")
                    .order_by("-conversation_count")
                )
            else:
                ab2_5_projects = (
                    ab2_5_query.annotate(conversation_count=Count("conversations"))
                    .values("uuid", "name", "conversation_count")
                    .order_by("-conversation_count")
                )

            ab2_5_list = list(ab2_5_projects)
            results["AB 2.5"] = {"count": len(ab2_5_list), "projects": ab2_5_list}

        serializer = ProjectsByMotorSerializer(results)
        return Response(serializer.data)
