import json

from django.db.models import Q
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission

from nexus.inline_agents.models import Agent
from nexus.usecases.agents.exceptions import SkillFileTooLarge
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.usecases.inline_agents.update import UpdateAgentUseCase

from nexus.projects.models import Project
from nexus.usecases.inline_agents.assign import AssignAgentsUsecase
from nexus.usecases.inline_agents.get import (
    GetInlineAgentsUsecase,
    GetInlineCredentialsUsecase,
    GetLogGroupUsecase
)

from nexus.inline_agents.api.serializers import (
    IntegratedAgentSerializer,
    AgentSerializer,
    ProjectCredentialsListSerializer
)
from nexus.projects.api.permissions import ProjectPermission

SKILL_FILE_SIZE_LIMIT = settings.SKILL_FILE_SIZE_LIMIT


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

    def _check_can_edit_official_agent(self, agents, user_email):
        for key in agents:
            agent_qs = Agent.objects.filter(slug=key, is_official=True)
            existing_official_agent = agent_qs.exists()
            can_edit = False
            for can_edit_email in settings.OFFICIAL_SMART_AGENT_EDITORS:
                if can_edit_email in user_email:
                    can_edit = True
                    break
            if existing_official_agent and not can_edit:
                return False
        return True

    def post(self, request, *args, **kwargs):
        agent_usecase = CreateAgentUseCase()
        update_agent_usecase = UpdateAgentUseCase()

        files, agents, project_uuid = self._validate_request(request)

        agents = agents["agents"]

        print(json.dumps(agents, indent=4, default=str))
        print(files)

        if not self._check_can_edit_official_agent(agents=agents, user_email=request.user.email):
            return Response({"error": f"Permission Error: You are not authorized to edit this official AI Agent {key}"}, status=403)

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
    permission_classes = [IsAuthenticated, ProjectPermission]

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

    permission_classes = [IsAuthenticated, ProjectPermission]

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
    permission_classes = [IsAuthenticated, ProjectPermission]

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
    permission_classes = [IsAuthenticated, ProjectPermission]

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

        agents = Agent.objects.filter(is_official=True, source_type=Agent.VTEX_APP)

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


class ProjectComponentsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        try:
            project = Project.objects.get(uuid=project_uuid)
            return Response({
                "use_components": project.use_components
            })
        except Project.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=404
            )

    def patch(self, request, project_uuid):
        use_components = request.data.get('use_components')

        if use_components is None:
            return Response(
                {"error": "use_components field is required"},
                status=400
            )

        try:
            project = Project.objects.get(uuid=project_uuid)
            project.use_components = use_components
            project.save()
            return Response({
                "message": "Project updated successfully",
                "use_components": use_components
            })
        except Project.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=404
            )


class LogGroupView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = request.query_params.get('project')
        agent_key = request.query_params.get('agent_key')
        tool_key = request.query_params.get('tool_key')

        if not project_uuid or not agent_key or not tool_key:
            return Response(
                {"error": "project, agent_key and tool_key are required"},
                status=400
            )
        try:
            usecase = GetLogGroupUsecase()
            log_group = usecase.get_log_group(project_uuid, agent_key, tool_key)
        except Agent.DoesNotExist:
            return Response(
                {"error": f"Agent {agent_key} not found in project {project_uuid}"},
                status=404
            )

        return Response({"log_group": log_group})


class MultiAgentView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        if not project_uuid:
            return Response(
                {"error": "project is required"},
                status=400
            )

        try:
            can_view = False
            for can_view_email in settings.MULTI_AGENTS_CAN_ACCESS:
                if can_view_email in request.user.email:
                    can_view = True
                    break

            project = Project.objects.get(uuid=project_uuid)
            return Response({
                "multi_agents": project.inline_agent_switch,
                "can_view": can_view
            })
        except Project.DoesNotExist:
            return Response(
                {"error": "Project not found"},
                status=404
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=500
            )

    def patch(self, request, project_uuid):
        multi_agents = request.data.get('multi_agents')
        if multi_agents is None:
            return Response(
                {"error": "multi_agents field is required"},
                status=400
            )

        can_access = False
        for can_access_email in settings.MULTI_AGENTS_CAN_ACCESS:
            if can_access_email in request.user.email:
                can_access = True
                break
        if not can_access:
            return Response(
                {"error": "You are not authorized to access this resource"},
                status=403
            )

        try:
            project = Project.objects.get(uuid=project_uuid)
            project.inline_agent_switch = multi_agents
            project.save()
            return Response(
                {"message": "Project updated successfully", "multi_agents": multi_agents}, status=200
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=500
            )
