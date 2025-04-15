import json

from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from nexus.inline_agents.models import Agent
from nexus.usecases.agents.exceptions import SkillFileTooLarge
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.usecases.inline_agents.update import UpdateAgentUseCase

from nexus.projects.models import Project
from nexus.usecases.inline_agents.assign import AssignAgentsUsecase
from nexus.usecases.inline_agents.get import (
    GetInlineAgentsUsecase,
    GetInlineCredentialsUsecase
)

from nexus.inline_agents.api.serializers import (
    IntegratedAgentSerializer,
    AgentSerializer,
    ProjectCredentialsListSerializer
)


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
        update_agent_usecase = UpdateAgentUseCase()

        files, agents, project_uuid = self._validate_request(request)

        agents = agents["agents"]

        print(json.dumps(agents, indent=4, default=str))
        print(files)

        try:
            project = Project.objects.get(uuid=project_uuid)
            for key in agents:
                agent_qs = Agent.objects.filter(slug=key, project=project)
                existing_agent = agent_qs.exists()
                if existing_agent:
                    print(f"[+ Updating agent {key} +]")
                    update_agent_usecase.update_agent(agent_qs.first(), agents[key], project, files)
                else:
                    print(f"[+ Creating agent {key} +]")
                    agent_usecase.create_agent(key, agents[key], project, files)

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
            query_filter = Q(name__icontains=search)
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
        # TODO: filter skills
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(is_official=True, source_type=Agent.PLATFORM)

        if search:
            query_filter = Q(name__icontains=search)
            agents = agents.filter(query_filter).distinct('uuid')

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class ProjectCredentialsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        usecase = GetInlineCredentialsUsecase()
        official_credentials, custom_credentials = usecase.get_credentials_by_project(project_uuid)
        return Response({
            "official_agents_credentials": ProjectCredentialsListSerializer(official_credentials, many=True).data,
            "my_agents_credentials": ProjectCredentialsListSerializer(custom_credentials, many=True).data
        })

    def patch(self, request, project_uuid):
        credentials_data = request.data

        updated_credentials = []
        for key, value in credentials_data.items():
            usecase = UpdateAgentUseCase()
            updated = usecase.update_credential_value(project_uuid, key, value)
            if updated:
                updated_credentials.append(key)
                
        return Response({
            "message": "Credentials updated successfully",
            "updated_credentials": updated_credentials
        })

    def post(self, request, project_uuid):
        credentials_data = request.data.get('credentials', [])
        agent_uuid = request.data.get('agent_uuid')

        if not agent_uuid or not credentials_data:
            return Response(
                {"error": "agent_uuid and credentials are required"},
                status=400
            )

        try:
            agent = Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            return Response(
                {"error": "Agent not found"},
                status=404
            )

        credentials = {}
        for cred_item in credentials_data:
            credentials.update({
                cred_item.get('name'): {
                    'label': cred_item.get('label'),
                    'placeholder': cred_item.get('placeholder'),
                    'is_confidential': cred_item.get('is_confidential', True),
                    'value': cred_item.get('value')
                },
            })

        created_credentials = CreateAgentUseCase().create_credentials(agent, Project.objects.get(uuid=project_uuid), credentials)

        return Response({
            "message": "Credentials created successfully",
            "created_credentials": created_credentials
        })

from rest_framework.permissions import IsAuthenticated, BasePermission
class InternalCommunicationPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.has_perm("users.can_communicate_internally")


class VtexAppActiveAgentsView(APIView):
    permission_classes = [InternalCommunicationPermission]

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


class VtexAppAgentsView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(project__uuid=project_uuid)

        if search:
            query_filter = Q(name__icontains=search)
            agents = agents.filter(query_filter).distinct('uuid')

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class VtexAppOfficialAgentsView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, *args, **kwargs):
        # TODO: filter skills
        project_uuid = kwargs.get("project_uuid")
        search = self.request.query_params.get("search")

        agents = Agent.objects.filter(is_official=True, source_type=Agent.PLATFORM)

        if search:
            query_filter = Q(name__icontains=search)
            agents = agents.filter(query_filter).distinct('uuid')

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class VTexAppTeamView(APIView):

    permission_classes = [InternalCommunicationPermission]

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


class VtexAppProjectCredentialsView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, project_uuid):
        usecase = GetInlineCredentialsUsecase()
        official_credentials, custom_credentials = usecase.get_credentials_by_project(project_uuid)
        return Response({
            "official_agents_credentials": ProjectCredentialsListSerializer(official_credentials, many=True).data,
            "my_agents_credentials": ProjectCredentialsListSerializer(custom_credentials, many=True).data
        })

    def patch(self, request, project_uuid):
        credentials_data = request.data

        updated_credentials = []
        for key, value in credentials_data.items():
            usecase = UpdateAgentUseCase()
            updated = usecase.update_credential_value(project_uuid, key, value)
            if updated:
                updated_credentials.append(key)
                
        return Response({
            "message": "Credentials updated successfully",
            "updated_credentials": updated_credentials
        })

    def post(self, request, project_uuid):
        credentials_data = request.data.get('credentials', [])
        agent_uuid = request.data.get('agent_uuid')

        if not agent_uuid or not credentials_data:
            return Response(
                {"error": "agent_uuid and credentials are required"},
                status=400
            )

        try:
            agent = Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            return Response(
                {"error": "Agent not found"},
                status=404
            )

        credentials = {}
        for cred_item in credentials_data:
            credentials.update({
                cred_item.get('name'): {
                    'label': cred_item.get('label'),
                    'placeholder': cred_item.get('placeholder'),
                    'is_confidential': cred_item.get('is_confidential', True),
                    'value': cred_item.get('value')
                },
            })

        created_credentials = CreateAgentUseCase().create_credentials(agent, Project.objects.get(uuid=project_uuid), credentials)

        return Response({
            "message": "Credentials created successfully",
            "created_credentials": created_credentials
        })
