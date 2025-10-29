import pendulum
from django.db.models import Count, Q
from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.intelligences.models import Conversation
from nexus.projects.models import Project
from nexus.projects.api.permissions import ProjectPermission

from .serializers import (
    ResolutionRateSerializer,
    IndividualResolutionRateSerializer,
    UnresolvedRateSerializer,
    ProjectsByMotorSerializer,
)

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
            return None, None, Response(
                {"error": "Invalid start_date format. Use YYYY-MM-DD"}, status=400
            )

    if not end_date_str:
        end_date = pendulum.now().date()
    else:
        end_date = parse_date(end_date_str)
        if not end_date:
            return None, None, Response(
                {"error": "Invalid end_date format. Use YYYY-MM-DD"}, status=400
            )

    if start_date > end_date:
        return None, None, Response(
            {"error": "start_date must be before or equal to end_date"}, status=400
        )

    return start_date, end_date, None


class ResolutionRateAverageView(APIView):
    permission_classes = [ProjectPermission]

    def get(self, request, project_uuid=None):
        """
        GET /api/projects/<project_uuid>/analytics/resolution-rate/average/
        
        Query params:
        - start_date (optional, YYYY-MM-DD): Data inicial
        - end_date (optional, YYYY-MM-DD): Data final  
        - motor (optional, "AB 2" | "AB 2.5"): Filtrar por motor específico
        - min_conversations (optional, int): Mínimo de conversas para considerar projeto
        """
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        motor = request.query_params.get("motor")
        min_conversations_str = request.query_params.get("min_conversations")

        # Validate and parse dates
        start_date, end_date, error_response = validate_and_parse_dates(
            start_date_str, end_date_str
        )
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
                return Response(
                    {"error": "min_conversations must be a valid integer"}, status=400
                )

        # Build base query
        conversations = Conversation.objects.filter(
            project__uuid=project_uuid,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).select_related("project")

        # Filter by motor if provided
        if motor:
            backend_value = MOTOR_BACKEND_MAP[motor]
            conversations = conversations.filter(project__agents_backend=backend_value)

        # Filter by min_conversations (count per project first)
        if min_conversations is not None:
            project_counts = (
                conversations.values("project__uuid")
                .annotate(count=Count("uuid"))
                .filter(count__gte=min_conversations)
            )
            project_uuids = [pc["project__uuid"] for pc in project_counts]
            conversations = conversations.filter(project__uuid__in=project_uuids)

        # Aggregate statistics
        stats = conversations.aggregate(
            total=Count("uuid"),
            resolved=Count("uuid", filter=Q(resolution="0")),
            unresolved=Count("uuid", filter=Q(resolution="1")),
            in_progress=Count("uuid", filter=Q(resolution="2")),
            unclassified=Count("uuid", filter=Q(resolution="3")),
            has_chat_room=Count("uuid", filter=Q(resolution="4")),
        )

        # Calculate rates (handle division by zero)
        total = stats["total"]
        resolved = stats["resolved"]
        unresolved = stats["unresolved"]

        resolution_rate = float(resolved / total) if total > 0 else 0.0
        unresolved_rate = float(unresolved / total) if total > 0 else 0.0

        response_data = {
            "resolution_rate": round(resolution_rate, 4),
            "unresolved_rate": round(unresolved_rate, 4),
            "total_conversations": total,
            "resolved_conversations": resolved,
            "unresolved_conversations": unresolved,
            "breakdown": {
                "resolved": stats["resolved"],
                "unresolved": stats["unresolved"],
                "in_progress": stats["in_progress"],
                "unclassified": stats["unclassified"],
                "has_chat_room": stats["has_chat_room"],
            },
            "filters": {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "motor": motor,
                "min_conversations": min_conversations,
            },
        }

        serializer = ResolutionRateSerializer(response_data)
        return Response(serializer.data)


class ResolutionRateIndividualView(APIView):
    permission_classes = [ProjectPermission]

    def get(self, request, project_uuid=None):
        """
        GET /api/projects/<project_uuid>/analytics/resolution-rate/individual/
        
        Query params: Same as average endpoint
        Returns: Array of project-level metrics
        """
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        motor = request.query_params.get("motor")
        min_conversations_str = request.query_params.get("min_conversations")

        # Validate and parse dates
        start_date, end_date, error_response = validate_and_parse_dates(
            start_date_str, end_date_str
        )
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
                return Response(
                    {"error": "min_conversations must be a valid integer"}, status=400
                )

        # Build base query
        conversations = Conversation.objects.filter(
            project__uuid=project_uuid,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).select_related("project")

        # Filter by motor if provided
        if motor:
            backend_value = MOTOR_BACKEND_MAP[motor]
            conversations = conversations.filter(project__agents_backend=backend_value)

        # Group by project and calculate metrics
        project_stats = (
            conversations.values(
                "project__uuid", "project__name", "project__agents_backend"
            )
            .annotate(
                total=Count("uuid"),
                resolved=Count("uuid", filter=Q(resolution="0")),
                unresolved=Count("uuid", filter=Q(resolution="1")),
            )
            .order_by("-total")
        )

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
            },
        }

        serializer = IndividualResolutionRateSerializer(response_data)
        return Response(serializer.data)


class UnresolvedRateView(APIView):
    permission_classes = [ProjectPermission]

    def get(self, request, project_uuid=None):
        """
        GET /api/projects/<project_uuid>/analytics/unresolved-rate/
        
        Query params: Same as average endpoint
        Returns: Unresolved rate metrics
        """
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        motor = request.query_params.get("motor")
        min_conversations_str = request.query_params.get("min_conversations")

        # Validate and parse dates
        start_date, end_date, error_response = validate_and_parse_dates(
            start_date_str, end_date_str
        )
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
                return Response(
                    {"error": "min_conversations must be a valid integer"}, status=400
                )

        # Build base query
        conversations = Conversation.objects.filter(
            project__uuid=project_uuid,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).select_related("project")

        # Filter by motor if provided
        if motor:
            backend_value = MOTOR_BACKEND_MAP[motor]
            conversations = conversations.filter(project__agents_backend=backend_value)

        # Filter by min_conversations
        if min_conversations is not None:
            project_counts = (
                conversations.values("project__uuid")
                .annotate(count=Count("uuid"))
                .filter(count__gte=min_conversations)
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
                "motor": motor,
                "min_conversations": min_conversations,
            },
        }

        serializer = UnresolvedRateSerializer(response_data)
        return Response(serializer.data)


class ProjectsByMotorView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/analytics/projects/by-motor/
        
        Query params:
        - motor ("AB 2" | "AB 2.5" | "both"): Qual motor buscar
        - start_date (optional, YYYY-MM-DD): Filtrar conversas por data
        - end_date (optional, YYYY-MM-DD): Filtrar conversas por data
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
            start_date, end_date, error_response = validate_and_parse_dates(
                start_date_str, end_date_str
            )
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
            ab2_query = Project.objects.filter(
                agents_backend="BedrockBackend", is_active=True
            )

            if date_filter:
                ab2_projects = (
                    ab2_query.annotate(
                        conversation_count=Count("conversations", filter=date_filter)
                    )
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
            ab2_5_query = Project.objects.filter(
                agents_backend="OpenAIBackend", is_active=True
            )

            if date_filter:
                ab2_5_projects = (
                    ab2_5_query.annotate(
                        conversation_count=Count("conversations", filter=date_filter)
                    )
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

