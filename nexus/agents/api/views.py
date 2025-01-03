from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

# from nexus.usecases.projects import get_project_by_uuid
from nexus.usecases.agents import AgentDTO, AgentUsecase
from nexus.agents.models import Agent, Team, ActiveAgent

from nexus.projects.api.permissions import ProjectPermission

from nexus.agents.api.serializers import ActiveAgentSerializer, ActiveAgentTeamSerializer


class PushAgents(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]

    def post(self, request, *args, **kwargs):
        # CLI will send a file and a dictionary of agents

        agents: dict = request.data.get("agents")

        usecase = AgentUsecase()
        agents_dto: list[AgentDTO] = usecase.yaml_dict_to_dto(agents)

        project_uuid = request.data.get("project")
        print(project_uuid)
        agents = []

        print("AGENTS DTO: ")
        print(agents_dto)

        for agent_dto in agents_dto:
            print('entrou no for')
            agent: Agent = AgentUsecase().create_agent(request.user, agent_dto, project_uuid)
            agents.append({"agent_name": agent.display_name, "agent_external_id": agent.external_id})

            skills = agent_dto.skills
            for skill in skills:
                slug = skill.get('slug')
                skill_file = request.FILES[slug]
                usecase.create_skill(skill_file)

        return Response({
            "project": str(project_uuid),
            "agents": agents
        })


class ActiveAgentsViewSet(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]
    serializer_class = ActiveAgentSerializer

    def patch(self, request, *args, **kwargs):

        project_uuid = request.data.get("project")
        agent_uuid = kwargs.get("agent_uuid")
        assigned: bool = request.data.get("assign")

        agent = Agent.objects.get(uuid=agent_uuid)
        team = Team.objects.get(project__uuid=project_uuid)

        if not assigned:
            active_agent = ActiveAgent.objects.get(
                agent=agent,
                team=team
            )
            active_agent.delete()
            return Response({"message": "Agent unassigned"})

        active_agent, created = ActiveAgent.objects.get_or_create(
            agent=agent,
            team=team,
            is_official=agent.is_official
        )
        serializer = ActiveAgentSerializer(active_agent)
        return Response(serializer.data)


class TeamViewset(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]
    serializer_class = ActiveAgentTeamSerializer

    def get(self, request, *args, **kwargs):

        project_uuid = kwargs.get("project_uuid")

        team = ActiveAgent.objects.filter(team__project__uuid=project_uuid)
        serializer = ActiveAgentTeamSerializer(team, many=True)
        return Response(serializer.data)
