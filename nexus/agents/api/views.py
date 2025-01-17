import json

from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

# from nexus.usecases.projects import get_project_by_uuid
from nexus.usecases.agents import AgentDTO, AgentUsecase, UpdateAgentDTO
from nexus.usecases.agents.exceptions import AgentInstructionsTooShort
from nexus.agents.models import Agent, Team, ActiveAgent

from nexus.projects.api.permissions import ProjectPermission

from nexus.agents.api.serializers import (
    AgentSerializer,
    ActiveAgentSerializer,
    ActiveAgentTeamSerializer,
)


class PushAgents(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]

    def post(self, request, *args, **kwargs):
        # CLI will send a file and a dictionary of agents

        print("----------------REQUEST STARTED----------------")
        print(request.data)
        print("-----------------------------------------------")
        agents: str = request.data.get("agents")
        agents: dict = json.loads(agents)

        project_uuid = request.data.get("project_uuid")

        usecase = AgentUsecase()
        agents_dto = usecase.agent_dto_handler(yaml=agents, project_uuid=project_uuid)

        if agents_dto is UpdateAgentDTO:
            updated_agent = usecase.update_agent(agents_dto, project_uuid)

            return Response({
                "project": str(project_uuid),
                "agents": updated_agent
            })


        agents_updated = []
        for agent_dto in agents_dto:
            agent, updated = AgentUsecase().create_agent(request.user, agent_dto, project_uuid)
            agents_updated.append({"agent_name": agent.display_name, "agent_external_id": agent.external_id})

            print("Agent created: ", agent.display_name)

            skills = agent_dto.skills
            if not updated:  # temp while there is no skill update
                for skill in skills:
                    slug = skill.get('slug')
                    skill_file = request.FILES[f"{agent.slug}:{slug}"]
                    print("------ Skill data ------")
                    print("Slug: ", slug)
                    print("Skill file: ", skill_file)
                    print("Skill file type: ", type(skill_file))

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

                    usecase.create_skill(
                        agent_external_id=agent.metadata["external_id"],
                        file_name=slug,
                        agent_version=agent.metadata.get("agentVersion"),
                        file=skill_file,
                        function_schema=function_schema,
                    )

        return Response({
            "project": str(project_uuid),
            "agents": agents_updated
        })


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
            # serializer = ActiveAgentSerializer(active_agent)
            return Response({"assigned": True})

        usecase.unassign_agent(agent_uuid=agent_uuid, project_uuid=project_uuid)
        return Response({"assigned": False})


class TeamViewset(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]
    serializer_class = ActiveAgentTeamSerializer

    def get(self, request, *args, **kwargs):

        project_uuid = kwargs.get("project_uuid")

        team = ActiveAgent.objects.filter(team__project__uuid=project_uuid)
        serializer = ActiveAgentTeamSerializer(team, many=True)
        return Response(serializer.data)


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
