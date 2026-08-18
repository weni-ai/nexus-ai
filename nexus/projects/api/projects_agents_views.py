from collections import defaultdict

from mozilla_django_oidc.contrib.drf import OIDCAuthentication
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.analytics.api.views import InternalCommunicationPermission
from nexus.authentication.authentication import ExternalTokenAuthentication
from nexus.inline_agents.api.serializers import inline_agent_list_display_name
from nexus.inline_agents.models import IntegratedAgent
from nexus.projects.models import Project
from nexus.projects.services.projects_resolution_rate import eligible_projects_queryset, parse_project_uuids
from nexus.users.api.authentication import UserGlobalTokenAuthentication


class ProjectAgentItemSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    is_official = serializers.BooleanField()


class ProjectsAgentsResultSerializer(serializers.Serializer):
    project_uuid = serializers.UUIDField()
    project_name = serializers.CharField()
    custom_agents_count = serializers.IntegerField()
    official_agents_count = serializers.IntegerField()
    agents = ProjectAgentItemSerializer(many=True)


class ProjectsAgentsResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = ProjectsAgentsResultSerializer(many=True)


class ProjectsAgentsView(APIView):
    authentication_classes = [UserGlobalTokenAuthentication, ExternalTokenAuthentication, OIDCAuthentication]
    permission_classes = [InternalCommunicationPermission]

    def get(self, request):
        if getattr(self, "swagger_fake_view", False):
            return Response({})

        try:
            project_uuids = parse_project_uuids(request.query_params.getlist("project_uuids"))
        except ValueError as exc:
            return Response({"project_uuids": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        if not project_uuids:
            return Response({"project_uuids": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)

        payload = _build_payload(project_uuids)
        serializer = ProjectsAgentsResponseSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(payload, status=status.HTTP_200_OK)


def _build_payload(project_uuids) -> dict:
    eligible = {project.uuid: project for project in eligible_projects_queryset(project_uuids)}
    projects = [eligible[uuid] for uuid in project_uuids if uuid in eligible]
    agents_by_project = _active_agents_by_project(projects)

    results = []
    for project in projects:
        agents = []
        custom_count = 0
        official_count = 0
        for integrated in agents_by_project.get(project.uuid, []):
            agent = integrated.agent
            item = {
                "uuid": str(agent.uuid),
                "name": inline_agent_list_display_name(agent),
                "slug": agent.slug,
                "is_official": agent.is_official,
            }
            agents.append(item)
            if agent.is_official:
                official_count += 1
            else:
                custom_count += 1
        agents.sort(key=lambda row: (not row["is_official"], row["name"].lower(), row["slug"]))
        results.append(
            {
                "project_uuid": str(project.uuid),
                "project_name": project.name,
                "custom_agents_count": custom_count,
                "official_agents_count": official_count,
                "agents": agents,
            }
        )

    return {"count": len(results), "results": results}


def _active_agents_by_project(projects: list[Project]) -> dict:
    if not projects:
        return {}

    rows = IntegratedAgent.objects.filter(
        project_id__in=[project.uuid for project in projects],
        is_active=True,
    ).select_related("agent", "agent__group", "agent__group__modal")

    grouped: dict = defaultdict(list)
    for row in rows:
        grouped[row.project_id].append(row)
    return grouped
