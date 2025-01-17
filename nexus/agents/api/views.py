import json

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from nexus.usecases.agents import AgentDTO, AgentUsecase
from nexus.agents.models import Agent

from nexus.projects.api.permissions import ProjectPermission


class PushAgents(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]

    def post(self, request, *args, **kwargs):
        # CLI will send a file and a dictionary of agents

        print("----------------REQUEST STARTED----------------")
        print(request.data)
        print("-----------------------------------------------")

        agents: str = request.data.get("agents")
        agents: dict = json.loads(agents)

        agents_usecase = AgentUsecase()
        agents_dto: list[AgentDTO] = agents_usecase.yaml_dict_to_dto(agents)

        project_uuid = request.data.get("project_uuid")

        agents_updated = []
        for agent_dto in agents_dto:
            agent: Agent = agents_usecase.create_agent(request.user, agent_dto, project_uuid)
            agents_updated.append({"agent_name": agent.display_name, "agent_external_id": agent.external_id})

            print("Agent created: ", agent.display_name)

            skills = agent_dto.skills

            for skill in skills:
                slug = skill.get('slug')
                skill_file = request.FILES[f"{agent.slug}:{slug}"]

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

        return Response({
            "project": str(project_uuid),
            "agents": agents_updated
        })
