import json

from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from nexus.agents.api.serializers import (
    ActiveAgentSerializer,
    ActiveAgentTeamSerializer,
    AgentSerializer,
)
from nexus.agents.models import (
    Agent,
    ActiveAgent,
    Team
)

from nexus.usecases.agents import (
    AgentDTO,
    AgentUsecase
)
from nexus.usecases.agents.exceptions import SkillFileTooLarge
from nexus.projects.api.permissions import ProjectPermission


class PushAgents(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]

    def post(self, request, *args, **kwargs):
        def validate_file_size(files):
            for file in files:
                if files[file].size > 10 * (1024**2):
                    raise SkillFileTooLarge(file)
        # CLI will send a file and a dictionary of agents

        print("----------------REQUEST STARTED----------------")
        print(request.data)
        print("-----------------------------------------------")

        files = request.FILES
        validate_file_size(files)

        agents: str = request.data.get("agents")
        agents: dict = json.loads(agents)

        agents_usecase = AgentUsecase()
        agents_dto: list[AgentDTO] = agents_usecase.yaml_dict_to_dto(agents, user_email=request.user.email)

        project_uuid = request.data.get("project_uuid")

        agents_updated = []
        for agent_dto in agents_dto:
            agent: Agent = agents_usecase.create_agent(request.user, agent_dto, project_uuid)
            agents_updated.append({"agent_name": agent.display_name, "agent_external_id": agent.external_id})

            print("Agent created: ", agent.display_name)

            skills = agent_dto.skills

            for skill in skills:
                slug = skill.get('slug')
                skill_file = files[f"{agent.slug}:{slug}"]

                # Convert InMemoryUploadedFile to bytes
                skill_file = skill_file.read()
                skill_parameters = skill.get("parameters")

                if type(skill_parameters) == list:
                    params = {}
                    for param in skill_parameters:
                        params.update(param)

                    skill_parameters = params

                slug = f"{slug}-{agent.external_id}"
                function_schema = [
                    {
                        "name": skill.get("slug"),
                        "parameters": skill_parameters,
                    }
                ]

                agents_usecase.create_skill(
                    agent_external_id=agent.metadata["external_id"],
                    file_name=slug,
                    agent_version=agent.metadata.get("agentVersion"),
                    file=skill_file,
                    function_schema=function_schema,
                )
        team = agents_usecase.get_team_object(project__uuid=project_uuid)
        return Response({
            "project": str(project_uuid),
            "agents": agents_updated,
            "supervisor_id": team.metadata.get("supervisor_alias_id"),
            "supervisor_alias": team.metadata.get("supervisor_alias_name"),
        })


class AgentsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

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


class ActiveAgentsViewSet(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]
    serializer_class = ActiveAgentSerializer

    def patch(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        agent_uuid = kwargs.get("agent_uuid")

        assign: bool = request.data.get("assigned")

        usecase = AgentUsecase()

        if assign:
            usecase.assign_agent(
                agent_uuid=agent_uuid,
                project_uuid=project_uuid,
                created_by=request.user
            )
            return Response({"assigned": True})

        usecase.unassign_agent(agent_uuid=agent_uuid, project_uuid=project_uuid)
        return Response({"assigned": False})


class OfficialAgentsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(is_official=True)

        if search:
            query_filter = Q(display_name__icontains=search) | Q(
                agent_skills__display_name__icontains=search
            )
            agents = agents.filter(query_filter).distinct('uuid')

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class TeamView(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]
    serializer_class = ActiveAgentTeamSerializer

    def get(self, request, *args, **kwargs):

        project_uuid = kwargs.get("project_uuid")

        team = Team.objects.get(project__uuid=project_uuid)
        team_agents = ActiveAgent.objects.filter(team=team)
        serializer = ActiveAgentTeamSerializer(team_agents, many=True)
        print(team.external_id)
        data = {
            "manager": {
                "external_id": team.external_id
            },
            "agents": serializer.data
        }
        return Response(data)
