from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from nexus.usecases.projects import get_project_by_uuid
from nexus.usecases.agents import AgentDTO, AgentUsecase
from nexus.agents.models import Agent

from nexus.projects.api.permissions import ProjectPermission


class PushAgents(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]

    def post(self, request, *args, **kwargs):
        def get_agents(agents):
            dto_list = []
            for agent_slug in agents:
                agent = agents.get(agent_slug)
                agent.update({"slug": agent_slug})
                dto_list.append(AgentDTO(**agent))
            return dto_list

        project_uuid = request.data.get("project")
        project = get_project_by_uuid(project_uuid)

        agents = request.data.get("agents")
        agents_dto = get_agents(agents)

        print(agents_dto)

        agents = []

        for agent_dto in agents_dto:
            agent: Agent = AgentUsecase().create_agent(request.user, agent_dto, project_uuid)

            agents.append({"agent_name": agent.display_name, "agent_external_id": agent.external_id})

        return Response({
            "project": str(project.uuid),
            "agents": agents
        })
