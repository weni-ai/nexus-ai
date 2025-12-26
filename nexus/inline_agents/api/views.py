import logging

from django.conf import settings
from django.db.models import Q
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from inline_agents.backends import BackendsRegistry
from nexus.events import event_manager, notify_async
from nexus.inline_agents.api.serializers import (
    AgentSerializer,
    IntegratedAgentSerializer,
    ProjectCredentialsListSerializer,
)
from nexus.inline_agents.models import Agent
from nexus.projects.api.permissions import CombinedExternalProjectPermission, ProjectPermission
from nexus.projects.models import Project
from nexus.usecases.agents.exceptions import SkillFileTooLarge
from nexus.usecases.inline_agents.assign import AssignAgentsUsecase
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.usecases.inline_agents.get import GetInlineAgentsUsecase, GetInlineCredentialsUsecase, GetLogGroupUsecase
from nexus.usecases.inline_agents.update import UpdateAgentUseCase
from nexus.usecases.intelligences.get_by_uuid import (
    create_inline_agents_configuration,
    get_project_and_content_base_data,
)
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from router.entities import message_factory

logger = logging.getLogger(__name__)

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

        logger.debug("InlineAgentsView payload", extra={"keys": list(request.data.keys())})

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
                return key
        return None

    def post(self, request, *args, **kwargs):
        agent_usecase = CreateAgentUseCase()
        update_agent_usecase = UpdateAgentUseCase()

        files, agents, project_uuid = self._validate_request(request)

        agents = agents["agents"]

        logger.debug("Agents payload", extra={"agent_keys": list(agents.keys()) if isinstance(agents, dict) else None})
        logger.debug("Files payload", extra={"file_count": len(files) if hasattr(files, "__len__") else None})
        official_agent_key = self._check_can_edit_official_agent(agents=agents, user_email=request.user.email)
        if official_agent_key is not None:
            return Response(
                {
                    "error": (
                        f"Permission Error: You are not authorized to edit an official "
                        f"AI Agent {official_agent_key}"
                    )
                },
                status=403,
            )

        try:
            project = Project.objects.get(uuid=project_uuid)
            for key in agents:
                agent_qs = Agent.objects.filter(slug=key, project=project)
                existing_agent = agent_qs.exists()
                if existing_agent:
                    logger.info("Updating agent", extra={"key": key})
                    update_agent_usecase.update_agent(agent_qs.first(), agents[key], project, files)
                else:
                    logger.info("Creating agent", extra={"key": key})
                    agent_usecase.create_agent(key, agents[key], project, files)

            # Fire cache invalidation event for team update (agents are part of team) (async observer)
            notify_async(
                event="cache_invalidation:team",
                project_uuid=project_uuid,
            )

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

                # Fire cache invalidation event for team update (agent assigned) (async observer)
                notify_async(
                    event="cache_invalidation:team",
                    project_uuid=project_uuid,
                )

                return Response({"assigned": True}, status=200)

            usecase.unassign_agent(agent_uuid, project_uuid)

            # Fire cache invalidation event for team update (agent unassigned) (async observer)
            notify_async(
                event="cache_invalidation:team",
                project_uuid=project_uuid,
            )

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
            agents = agents.filter(query_filter).distinct("uuid")

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class TeamView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        usecase = GetInlineAgentsUsecase()
        agents = usecase.get_active_agents(project_uuid)
        serializer = IntegratedAgentSerializer(agents, many=True)

        data = {"manager": {"external_id": ""}, "agents": serializer.data}
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
            agents = agents.filter(query_filter).distinct("uuid")

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class ProjectCredentialsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        usecase = GetInlineCredentialsUsecase()
        official_credentials, custom_credentials = usecase.get_credentials_by_project(project_uuid)
        return Response(
            {
                "official_agents_credentials": ProjectCredentialsListSerializer(official_credentials, many=True).data,
                "my_agents_credentials": ProjectCredentialsListSerializer(custom_credentials, many=True).data,
            }
        )

    def patch(self, request, project_uuid):
        credentials_data = request.data

        updated_credentials = []
        for key, value in credentials_data.items():
            usecase = UpdateAgentUseCase()
            updated = usecase.update_credential_value(project_uuid, key, value)
            if updated:
                updated_credentials.append(key)

        return Response({"message": "Credentials updated successfully", "updated_credentials": updated_credentials})

    def post(self, request, project_uuid):
        credentials_data = request.data.get("credentials", [])
        agent_uuid = request.data.get("agent_uuid")

        if not agent_uuid or not credentials_data:
            return Response({"error": "agent_uuid and credentials are required"}, status=400)

        try:
            agent = Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        credentials = {}
        for cred_item in credentials_data:
            credentials.update(
                {
                    cred_item.get("name"): {
                        "label": cred_item.get("label"),
                        "placeholder": cred_item.get("placeholder"),
                        "is_confidential": cred_item.get("is_confidential", True),
                        "value": cred_item.get("value"),
                    },
                }
            )

        created_credentials = CreateAgentUseCase().create_credentials(
            agent, Project.objects.get(uuid=project_uuid), credentials
        )

        return Response({"message": "Credentials created successfully", "created_credentials": created_credentials})


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

                # Fire cache invalidation event for team update (agent assigned)
                notify_async(
                    event="cache_invalidation:team",
                    project_uuid=project_uuid,
                )

                return Response({"assigned": True}, status=200)

            usecase.unassign_agent(agent_uuid, project_uuid)

            # Fire cache invalidation event for team update (agent unassigned)
            notify_async(
                event="cache_invalidation:team",
                project_uuid=project_uuid,
            )

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
            agents = agents.filter(query_filter).distinct("uuid")

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
            agents = agents.filter(query_filter).distinct("uuid")

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class VTexAppTeamView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        usecase = GetInlineAgentsUsecase()
        agents = usecase.get_active_agents(project_uuid)
        serializer = IntegratedAgentSerializer(agents, many=True)

        data = {"manager": {"external_id": ""}, "agents": serializer.data}
        return Response(data)


class VtexAppProjectCredentialsView(APIView):
    permission_classes = [InternalCommunicationPermission]

    def get(self, request, project_uuid):
        usecase = GetInlineCredentialsUsecase()
        official_credentials, custom_credentials = usecase.get_credentials_by_project(project_uuid)
        return Response(
            {
                "official_agents_credentials": ProjectCredentialsListSerializer(official_credentials, many=True).data,
                "my_agents_credentials": ProjectCredentialsListSerializer(custom_credentials, many=True).data,
            }
        )

    def patch(self, request, project_uuid):
        credentials_data = request.data

        updated_credentials = []
        for key, value in credentials_data.items():
            usecase = UpdateAgentUseCase()
            updated = usecase.update_credential_value(project_uuid, key, value)
            if updated:
                updated_credentials.append(key)

        return Response({"message": "Credentials updated successfully", "updated_credentials": updated_credentials})

    def post(self, request, project_uuid):
        credentials_data = request.data.get("credentials", [])
        agent_uuid = request.data.get("agent_uuid")

        if not agent_uuid or not credentials_data:
            return Response({"error": "agent_uuid and credentials are required"}, status=400)

        try:
            agent = Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        credentials = {}
        for cred_item in credentials_data:
            credentials.update(
                {
                    cred_item.get("name"): {
                        "label": cred_item.get("label"),
                        "placeholder": cred_item.get("placeholder"),
                        "is_confidential": cred_item.get("is_confidential", True),
                        "value": cred_item.get("value"),
                    },
                }
            )

        created_credentials = CreateAgentUseCase().create_credentials(
            agent, Project.objects.get(uuid=project_uuid), credentials
        )

        return Response({"message": "Credentials created successfully", "created_credentials": created_credentials})


class ProjectComponentsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        try:
            project = Project.objects.get(uuid=project_uuid)
            return Response({"use_components": project.use_components})
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)

    def patch(self, request, project_uuid):
        use_components = request.data.get("use_components")

        if use_components is None:
            return Response({"error": "use_components field is required"}, status=400)

        try:
            project = Project.objects.get(uuid=project_uuid)
            project.use_components = use_components
            project.save()

            # Fire cache invalidation event for project update
            event_manager.notify(
                event="cache_invalidation:project",
                project=project,
            )

            return Response({"message": "Project updated successfully", "use_components": use_components})
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)


class LogGroupView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = request.query_params.get("project")
        agent_key = request.query_params.get("agent_key")
        tool_key = request.query_params.get("tool_key")

        if not project_uuid or not agent_key or not tool_key:
            return Response({"error": "project, agent_key and tool_key are required"}, status=400)
        try:
            usecase = GetLogGroupUsecase()
            log_group = usecase.get_log_group(project_uuid, agent_key, tool_key)
        except Agent.DoesNotExist:
            return Response({"error": f"Agent {agent_key} not found in project {project_uuid}"}, status=404)

        return Response({"log_group": log_group})


class MultiAgentView(APIView):
    permission_classes = [CombinedExternalProjectPermission]
    authentication_classes = []  # Disable default authentication

    def get(self, request, project_uuid):
        if not project_uuid:
            return Response({"error": "project is required"}, status=400)

        try:
            project = Project.objects.get(uuid=project_uuid)

            return Response(
                {
                    "multi_agents": project.inline_agent_switch,
                }
            )
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

    def patch(self, request, project_uuid):
        multi_agents = request.data.get("multi_agents")
        if multi_agents is None:
            return Response({"error": "multi_agents field is required"}, status=400)

        try:
            project = Project.objects.get(uuid=project_uuid)

            # AB 1.0 projects have inline_agent_switch=False and use BedrockBackend
            is_legacy_project_enabling = (
                not project.inline_agent_switch and multi_agents and project.agents_backend == "BedrockBackend"
            )
            project.inline_agent_switch = multi_agents
            # Migrate legacy projects (AB 1.0) to AB 2.5 (OpenAI)
            if is_legacy_project_enabling:
                project.agents_backend = "OpenAIBackend"

            if not project.use_prompt_creation_configurations:
                project.use_prompt_creation_configurations = True
            project.save()

            # Fire cache invalidation event for project update (async observer)
            notify_async(
                event="cache_invalidation:project",
                project=project,
            )

            return Response({"message": "Project updated successfully", "multi_agents": multi_agents}, status=200)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


class AgentEndSessionView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def post(self, request, project_uuid):
        contact_urn = request.data.get("contact_urn")
        if not contact_urn:
            return Response({"error": "contact_urn is required"}, status=400)

        message_obj = message_factory(text="", project_uuid=project_uuid, contact_urn=contact_urn)

        projects_use_case = ProjectsUseCase()
        agents_backend = projects_use_case.get_agents_backend_by_project(project_uuid)
        backend = BackendsRegistry.get_backend(agents_backend)
        backend.end_session(message_obj.project_uuid, message_obj.sanitized_urn)
        return Response({"message": "Agent session ended successfully"})


class AgentBuilderAudio(APIView):
    def get(self, request, project_uuid):
        _, _, inline_agents_configuration = get_project_and_content_base_data(project_uuid=project_uuid)
        if inline_agents_configuration:
            return Response(
                {
                    "audio_orchestration": inline_agents_configuration.audio_orchestration,
                    "agent_voice": inline_agents_configuration.audio_orchestration_voice,
                }
            )

        return Response({"audio_orchestration": False, "agent_voice": None})

    def post(self, request, project_uuid):
        agent_voice = request.data.get("agent_voice")
        audio_orchestration = request.data.get("audio_orchestration")

        if not agent_voice and audio_orchestration is None:
            return Response({"error": "At least one of 'audio_orchestration' or 'agent_voice' is required"}, status=400)

        try:
            project, _, inline_agents_configuration = get_project_and_content_base_data(project_uuid=project_uuid)

            if inline_agents_configuration is None:
                inline_agents_configuration = create_inline_agents_configuration(
                    project, audio_orchestration=audio_orchestration, audio_orchestration_voice=agent_voice
                )

            if audio_orchestration is not None and agent_voice:
                inline_agents_configuration.set_audio_orchestration(audio_orchestration, agent_voice)

            elif audio_orchestration is not None:
                inline_agents_configuration.set_audio_orchestration(audio_orchestration)

            elif agent_voice:
                inline_agents_configuration.set_audio_orchestration_voice(agent_voice)

            # Fire cache invalidation event for project update (async observer)
            notify_async(
                event="cache_invalidation:project",
                project=project,
            )

            return Response(
                {
                    "audio_orchestration": inline_agents_configuration.audio_orchestration,
                    "agent_voice": inline_agents_configuration.audio_orchestration_voice,
                },
                status=200,
            )

        except ValueError:
            return Response({"error": "Invalid voice option"}, status=400)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
