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
    Team,
)

from nexus.usecases.agents import (
    AgentUsecase,
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
        print(["+ Pushing Agents +"])
        print("----------------REQUEST STARTED----------------")
        print(request.data)
        print("-----------------------------------------------")

        files = request.FILES
        validate_file_size(files)

        agents: str = request.data.get("agents")
        agents: dict = json.loads(agents)

        project_uuid = request.data.get("project_uuid")
        agents_usecase = AgentUsecase()

        team = agents_usecase.get_team_object(project__uuid=project_uuid)
        agents_dto = agents_usecase.agent_dto_handler(
            yaml=agents,
            project_uuid=project_uuid,
            user_email=request.user.email
        )

        agents_updated = []
        response_warnings = []
        for agent_dto in agents_dto:
            if hasattr(agent_dto, 'is_update') and agent_dto.is_update:
                # Handle update
                agent = agents_usecase.update_agent(
                    agent_dto=agent_dto,
                    project_uuid=project_uuid
                )

                # Handle skills if present
                if agent_dto.skills:
                    for skill in agent_dto.skills:
                        skill_file = files[f"{agent.slug}:{skill['slug']}"]
                        function_schema = self._create_function_schema(skill)
                        skill_handler = skill.get("source").get("entrypoint")
                        if skill['is_update']:
                            # Update existing skill
                            agent_version = agent.current_version.metadata.get("agent_alias_version")
                            warnings = agents_usecase.update_skill(
                                file_name=f"{skill['slug']}-{agent.external_id}",
                                agent_external_id=agent.external_id,
                                agent_version=agent_version,
                                file=skill_file.read(),
                                function_schema=function_schema,
                                user=request.user,
                                skill_handler=skill_handler
                            )
                            if warnings:
                                response_warnings.extend(warnings)
                        else:
                            # Create new skill
                            agent_version = agent.current_version.metadata.get("agent_alias_version")
                            agents_usecase.create_skill(
                                agent_external_id=agent.metadata["external_id"],
                                file_name=f"{skill['slug']}-{agent.external_id}",
                                agent_version=agent_version,
                                file=skill_file.read(),
                                function_schema=function_schema,
                                user=request.user,
                                agent=agent,
                                skill_handler=skill_handler
                            )

                agents_updated.append({
                    "agent_name": agent.display_name,
                    "agent_external_id": agent.external_id
                })

                agents_usecase.prepare_agent(agent.external_id)
                agents_usecase.external_agent_client.agent_for_amazon_bedrock.wait_agent_status_update(agent.external_id)
                agents_usecase.create_agent_version(agent.external_id, request.user, agent)

                if ActiveAgent.objects.filter(team__project__uuid=project_uuid, agent=agent).exists():
                    agents_usecase.update_supervisor_collaborator(project_uuid, agent)
                    agents_usecase.create_supervisor_version(project_uuid, request.user)

                continue

            # Handle new agent creation
            external_id = agents_usecase.create_agent(
                user=request.user,
                agent_dto=agent_dto,
                project_uuid=project_uuid
            )

            print(f"[+ Agent created {external_id} +]")

            # Create skills for new agent if present
            agent = Agent.objects.create(
                created_by=request.user,
                project_id=project_uuid,
                external_id=external_id,
                slug=agent_dto.slug,
                display_name=agent_dto.name,
                model=agent_dto.model,
                description=agent_dto.description,
            )
            agent.create_version(
                agent_alias_id="DRAFT",
                agent_alias_name="DRAFT",
                agent_alias_arn="DRAFT",
                agent_alias_version="DRAFT",
            )

            if agent_dto.skills:
                warnings = agents_usecase.handle_agent_skills(
                    agent=agent,
                    skills=agent_dto.skills,
                    files=files,
                    user=request.user,
                )
                if warnings:
                    response_warnings.extend(warnings)

            alias_name = "v1"

            agents_usecase.external_agent_client.agent_for_amazon_bedrock.wait_agent_status_update(external_id)
            agents_usecase.prepare_agent(external_id)
            agents_usecase.external_agent_client.agent_for_amazon_bedrock.wait_agent_status_update(external_id)

            sub_agent_alias_id, sub_agent_alias_arn, agent_alias_version = agents_usecase.create_external_agent_alias(
                agent_id=external_id, alias_name=alias_name
            )

            agent.metadata.update(
                {
                    "engine": "BEDROCK",
                    "external_id": external_id,
                    "agent_alias_id": sub_agent_alias_id,
                    "agent_alias_arn": sub_agent_alias_arn,
                    "agentVersion": str(agent_alias_version),
                }
            )
            agent.create_version(
                agent_alias_id=sub_agent_alias_id,
                agent_alias_name=alias_name,
                agent_alias_arn=sub_agent_alias_arn,
                agent_alias_version=agent_alias_version,
            )

            agents_updated.append({
                "agent_name": agent.display_name,
                "agent_external_id": agent.external_id
            })

        team.refresh_from_db()

        response = {
            "project": str(project_uuid),
            "agents": agents_updated,
            "supervisor_id": team.metadata.get("supervisor_alias_id"),
            "supervisor_alias": team.metadata.get("supervisor_alias_name"),
        }

        if response_warnings:
            response["warnings"] = list(set(response_warnings))

        return Response(response)

    def _create_function_schema(self, skill: dict) -> list[dict]:
        """Helper method to create function schema from skill data"""
        skill_parameters = skill.get("parameters")
        if isinstance(skill_parameters, list):
            params = {}
            for param in skill_parameters:
                params.update(param)
            skill_parameters = params

        return [{
            "name": skill.get("slug"),
            "parameters": skill_parameters,
        }]


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
        user = request.user
        assign: bool = request.data.get("assigned")

        usecase = AgentUsecase()

        if assign:
            print("------------------------ UPDATING AGENT ---------------------")
            # usecase.update_agent_to_supervisor(team.external_id)
            usecase.assign_agent(
                agent_uuid=agent_uuid,
                project_uuid=project_uuid,
                created_by=user
            )
            usecase.create_supervisor_version(project_uuid, user)
            return Response({"assigned": True})

        usecase.unassign_agent(agent_uuid=agent_uuid, project_uuid=project_uuid)
        usecase.create_supervisor_version(project_uuid, user)
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
        return Response(serializer.data)
