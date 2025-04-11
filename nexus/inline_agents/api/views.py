import json

from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from nexus.inline_agents.models import Agent
from nexus.usecases.agents.exceptions import SkillFileTooLarge
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.projects.models import Project
from nexus.usecases.inline_agents.assign import AssignAgentsUsecase
from nexus.usecases.inline_agents.get import GetInlineAgentsUsecase

from nexus.inline_agents.api.serializers import IntegratedAgentSerializer, AgentSerializer


SKILL_FILE_SIZE_LIMIT = 10
# TODO: ProjectPermission


class PushAgents(APIView):
    permission_classes = [IsAuthenticated]

    def _validate_request(self, request):
        """Validate request data and return processed inputs"""
        def validate_file_size(files):
            for file in files:
                if files[file].size > SKILL_FILE_SIZE_LIMIT * (1024**2):
                    raise SkillFileTooLarge(file)

        files = request.FILES
        validate_file_size(files)

        import json
        print(json.dumps(request.data, indent=4, default=str))

        agents = json.loads(request.data.get("agents"))
        project_uuid = request.data.get("project_uuid")

        return files, agents, project_uuid


    def post(self, request, *args, **kwargs):
        agent_usecase = CreateAgentUseCase()
        files, agents, project_uuid = self._validate_request(request)
        agents = agents["agents"]

        try:
            project = Project.objects.get(uuid=project_uuid)
            for key in agents:
                agent = agents[key]
                agent_usecase.create_agent(key, agent, project, files)

        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)

        return Response({})


class ActiveAgentsView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        agent_uuid = kwargs.get("agent_uuid")
        assign: bool = request.data.get("assigned")

        usecase = AssignAgentsUsecase()

        try:
            if assign:
                usecase.assign_agent(agent_uuid, project_uuid)
                return Response({"assigned": True}, status=200)

            usecase.unassign_agent(agent_uuid, project_uuid)
            return Response({"assigned": False}, status=200)
        except ValueError as e:
            return Response({"error": str(e)}, status=404)


class AgentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(project__uuid=project_uuid)

        if search:
            query_filter = Q(display_name__icontains=search) | Q(
                agent_skills__display_name__icontains=search
            )
            agents = agents.filter(query_filter).distinct('uuid')

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class TeamView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):

        project_uuid = kwargs.get("project_uuid")
        usecase = GetInlineAgentsUsecase()
        agents = usecase.get_active_agents(project_uuid)
        serializer = IntegratedAgentSerializer(agents, many=True)

        data = {
            "manager": {
                "external_id": ""
            },
            "agents": serializer.data
        }
        return Response(data)


class OfficialAgentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        # agents = Agent.objects.filter(is_official=True, source_type=Agent.PLATFORM)
        agents = Agent.objects.filter(is_official=True)

        if search:
            query_filter = Q(display_name__icontains=search) | Q(
                agent_skills__display_name__icontains=search
            )
            agents = agents.filter(query_filter).distinct('uuid')

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)
