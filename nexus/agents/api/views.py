import json
import logging

from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission

from nexus.agents.encryption import encrypt_value, decrypt_value

from nexus.agents.api.serializers import (
    ActiveAgentSerializer,
    ActiveAgentTeamSerializer,
    AgentSerializer,
    ProjectCredentialsListSerializer,
)
from nexus.agents.models import (
    Agent,
    ActiveAgent,
    Team,
    Credential,
)

from nexus.usecases.agents import (
    AgentUsecase,
)
from nexus.usecases.agents.exceptions import SkillFileTooLarge
from nexus.projects.api.permissions import ProjectPermission


class InternalCommunicationPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.has_perm("users.can_communicate_internally")


class PushAgents(APIView):

    permission_classes = [IsAuthenticated, ProjectPermission]

    def _handle_agent_credentials(self, agent_dto, project_uuid, agent):
        """Helper method to handle agent credentials creation and updates.

        Args:
            agent_dto: The agent data transfer object containing credentials
            project_uuid: UUID of the project
            agent: Agent instance to associate credentials with

        Returns:
            list: List of warning messages for existing credentials
        """
        if not agent_dto.credentials:
            return []

        warnings = []
        print('-----------------Agent Credentials------------------')
        for credential_dict in agent_dto.credentials:
            for key, properties in credential_dict.items():
                props = {}
                for prop in properties:
                    if isinstance(prop, dict):
                        props.update(prop)

                try:
                    existing_credential = Credential.objects.filter(
                        project_id=project_uuid,
                        key=key
                    ).first()

                    if existing_credential:
                        warnings.append(f"Credential '{key}' already exists for this project")

                    credential, created = Credential.objects.get_or_create(
                        project_id=project_uuid,
                        key=key,
                        defaults={
                            "label": props.get("label", key),
                            "is_confidential": props.get("is_confidential", True),
                            "placeholder": props.get("placeholder", None),
                        }
                    )

                    if not created:
                        # Update existing credential properties
                        credential.label = props.get("label", key)
                        credential.placeholder = props.get("placeholder", None)

                        new_confidential = props.get("is_confidential", True)
                        if new_confidential != credential.is_confidential:
                            if new_confidential:
                                credential.value = encrypt_value(credential.value)
                            else:
                                credential.value = decrypt_value(credential.value)

                        credential.is_confidential = props.get("is_confidential", True)

                        credential.save(update_fields=['label', 'is_confidential', 'placeholder', 'value'])

                    credential.agents.add(agent)

                    print(key)

                except Exception as e:
                    error_message = str(e)
                    warnings.append(f"Error processing credential '{key}': {error_message}")
                    print(f"Error processing credential '{key}': {error_message}")
                    continue

        print('----------------------------------------------------')
        return warnings

    def _validate_request(self, request):
        """Validate request data and return processed inputs"""
        def validate_file_size(files):
            for file in files:
                if files[file].size > 10 * (1024**2):
                    raise SkillFileTooLarge(file)

        files = request.FILES
        validate_file_size(files)

        agents = json.loads(request.data.get("agents"))
        project_uuid = request.data.get("project_uuid")

        return files, agents, project_uuid

    def _handle_agent_update(self, agent_dto, project_uuid, files, request, team):
        """Handle updating an existing agent"""
        agents_usecase = AgentUsecase()
        response_warnings = []

        # Update agent
        agent = agents_usecase.update_agent(
            agent_dto=agent_dto,
            project_uuid=project_uuid
        )

        # Handle credentials
        credential_warnings = self._handle_agent_credentials(agent_dto, project_uuid, agent)
        if credential_warnings:
            response_warnings.extend(credential_warnings)

        # Handle skills
        if agent_dto.skills:
            for skill in agent_dto.skills:
                try:
                    warnings = self._process_skill(
                        skill=skill,
                        agent=agent,
                        files=files,
                        request=request,
                        project_uuid=project_uuid,
                        is_update=True
                    )
                    if warnings:
                        response_warnings.extend(warnings)
                except Exception as e:
                    # For updates, we log errors but continue processing
                    response_warnings.append(f"Error updating skill {skill['slug']}: {str(e)}")

        # Update agent versions and supervisor if needed
        self._update_agent_versions(agent, project_uuid, team, request)

        return agent, response_warnings

    def _update_agent_versions(self, agent, project_uuid, team, request):
        """Update agent versions and supervisor if needed"""
        agents_usecase = AgentUsecase()
        agents_usecase.prepare_agent(agent.external_id)
        agents_usecase.external_agent_client.wait_agent_status_update(agent.external_id)
        agents_usecase.create_agent_version(agent.external_id, request.user, agent, team)

        if ActiveAgent.objects.filter(agent=agent, team=team).exists():
            agents_usecase.update_supervisor_collaborator(project_uuid, agent)
            agents_usecase.create_agent_version(agent.external_id, request.user, agent, team)

    def _handle_agent_creation(self, agent_dto, project_uuid, files, request):
        """Handle creating a new agent with rollback on failure"""
        agents_usecase = AgentUsecase()
        response_warnings = []
        created_agent = None
        logger = logging.getLogger(__name__)

        try:
            # Create external agent first
            external_id = agents_usecase.create_agent(
                user=request.user,
                agent_dto=agent_dto,
                project_uuid=project_uuid
            )

            # Create local agent record
            created_agent = Agent.objects.create(
                created_by=request.user,
                project_id=project_uuid,
                external_id=external_id,
                slug=agent_dto.slug,
                display_name=agent_dto.name,
                model=agent_dto.model,
                description=agent_dto.description,
            )
            logger.debug(f"Created agent - PK: {created_agent.pk}, UUID: {created_agent.uuid}, Slug: {created_agent.slug}")

            created_agent.create_version(
                agent_alias_id="DRAFT",
                agent_alias_name="DRAFT",
                agent_alias_arn="DRAFT",
                agent_alias_version="DRAFT",
            )

            # Handle credentials
            credential_warnings = self._handle_agent_credentials(agent_dto, project_uuid, created_agent)
            if credential_warnings:
                response_warnings.extend(credential_warnings)

            # Handle skills
            if agent_dto.skills:
                for skill in agent_dto.skills:
                    try:
                        logger.debug(f"Processing skill {skill['slug']} for agent {created_agent.pk}")
                        warnings = self._process_skill(
                            skill=skill,
                            agent=created_agent,
                            files=files,
                            request=request,
                            project_uuid=project_uuid,
                            is_update=False
                        )
                        if warnings:
                            response_warnings.extend(warnings)
                    except Exception as e:
                        logger.error(f"Error during skill creation: {str(e)}")
                        logger.error(f"Agent state during rollback - PK: {created_agent.pk}, UUID: {created_agent.uuid}")
                        # If skill creation fails, rollback everything and re-raise the original exception
                        if created_agent and created_agent.pk:
                            self._rollback_agent_creation(created_agent, external_id)
                        raise  # Re-raise the original exception

            # Create agent alias and update metadata
            self._finalize_agent_creation(created_agent, external_id)

            return created_agent, response_warnings

        except Exception as e:
            if created_agent and created_agent.pk:
                self._rollback_agent_creation(created_agent, external_id)
            raise

    def _process_skill(self, skill, agent, files, request, project_uuid, is_update):
        """Process a single skill for an agent"""
        agents_usecase = AgentUsecase()
        skill_file = files[f"{agent.slug}:{skill['slug']}"]
        function_schema = self._create_function_schema(skill, project_uuid)
        skill_handler = skill.get("source").get("entrypoint")
        agent_version = agent.current_version.metadata.get("agent_alias_version")

        if is_update and skill.get('is_update'):
            return agents_usecase.update_skill(
                file_name=f"{skill['slug']}-{agent.external_id}",
                agent_external_id=agent.external_id,
                agent_version=agent_version,
                file=skill_file.read(),
                function_schema=function_schema,
                user=request.user,
                skill_handler=skill_handler
            )
        else:
            agents_usecase.create_skill(
                agent_external_id=agent.external_id,
                file_name=f"{skill['slug']}-{agent.external_id}",
                agent_version=agent_version,
                file=skill_file.read(),
                function_schema=function_schema,
                user=request.user,
                agent=agent,
                skill_handler=skill_handler
            )
            return []

    def _rollback_agent_creation(self, agent, external_id):
        """Rollback agent creation in case of failure"""
        logger = logging.getLogger(__name__)

        logger.warning(f"Rolling back agent creation for agent {agent.slug} (external_id: {external_id})")
        agents_usecase = AgentUsecase()

        try:
            # Delete the external agent
            agents_usecase.external_agent_client.delete_agent(external_id)
        except Exception as e:
            logger.error(f"Failed to delete external agent {external_id}: {str(e)}")
            # Continue with local cleanup despite external deletion failure

        try:
            # Delete the local agent record
            agent.delete()
        except Exception as e:
            logger.error(f"Failed to delete local agent {agent.slug}: {str(e)}")
            raise  # Re-raise the exception since we can't guarantee cleanup

    def post(self, request, *args, **kwargs):
        """Handle agent creation and updates"""
        try:
            # Validate and process request data
            files, agents_data, project_uuid = self._validate_request(request)

            # Initialize usecase and get team
            agents_usecase = AgentUsecase()
            team = agents_usecase.get_team_object(project__uuid=project_uuid)

            # Process agents
            agents_dto = agents_usecase.agent_dto_handler(
                yaml=agents_data,
                project_uuid=project_uuid,
                user_email=request.user.email
            )

            agents_updated = []
            response_warnings = []

            # Process each agent
            for agent_dto in agents_dto:
                if hasattr(agent_dto, 'is_update') and agent_dto.is_update:
                    agent, warnings = self._handle_agent_update(
                        agent_dto, project_uuid, files, request, team
                    )
                else:
                    agent, warnings = self._handle_agent_creation(
                        agent_dto, project_uuid, files, request
                    )

                response_warnings.extend(warnings)
                agents_updated.append({
                    "agent_name": agent.display_name,
                    "agent_external_id": agent.external_id
                })

            # Prepare response
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

        except Exception as e:
            # Log the error and return appropriate error response
            logger = logging.getLogger(__name__)
            logger.error(f"Error in PushAgents: {e}", exc_info=True)
            error_message = f"{e.__class__.__name__}: {str(e)}" if str(e) else str(e.__class__.__name__)
            return Response(
                {"error": error_message},
                status=500
            )

    def _create_function_schema(self, skill: dict, project_uuid: str) -> list[dict]:
        """Helper method to create function schema from skill data"""
        skill_parameters = skill.get("parameters")
        fields = []

        if isinstance(skill_parameters, list):
                params = {}
                for param in skill_parameters:
                    for key, value in param.items():
                        if value.get("contact_field"):
                            fields.append({
                                "key": key,
                                "value_type": value.get("type")
                            })
                        param[key].pop("contact_field", None)
                    params.update(param)
                skill_parameters = params

        agents_usecase = AgentUsecase()
        agents_usecase.create_contact_fields(project_uuid, fields)

        return [{
            "name": skill.get("slug"),
            "parameters": skill_parameters,
        }]

    def _finalize_agent_creation(self, agent, external_id):
        """Finalize agent creation by creating alias and updating metadata"""
        agents_usecase = AgentUsecase()

        # Wait for agent to be ready and prepare it
        agents_usecase.external_agent_client.wait_agent_status_update(external_id)
        agents_usecase.prepare_agent(external_id)
        agents_usecase.external_agent_client.wait_agent_status_update(external_id)

        # Create initial version (v1)
        alias_name = "v1"
        sub_agent_alias_id, sub_agent_alias_arn, agent_alias_version = agents_usecase.create_external_agent_alias(
            agent_id=external_id, 
            alias_name=alias_name
        )

        # Update agent metadata
        agent.metadata.update({
            "engine": "BEDROCK",
            "external_id": external_id,
            "agent_alias_id": sub_agent_alias_id,
            "agent_alias_arn": sub_agent_alias_arn,
            "agentVersion": str(agent_alias_version),
        })

        # Create version record
        agent.create_version(
            agent_alias_id=sub_agent_alias_id,
            agent_alias_name=alias_name,
            agent_alias_arn=sub_agent_alias_arn,
            agent_alias_version=agent_alias_version,
        )


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


class VtexAppAgentsView(APIView):
    permission_classes = [InternalCommunicationPermission]

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


class VtexAppActiveAgentsViewSet(APIView):

    permission_classes = [InternalCommunicationPermission]
    serializer_class = ActiveAgentSerializer

    def patch(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        agent_uuid = kwargs.get("agent_uuid")
        user = request.user
        assign: bool = request.data.get("assigned")

        usecase = AgentUsecase()

        if assign:
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

        agents = Agent.objects.filter(is_official=True, type=Agent.PLATFORM)

        if search:
            query_filter = Q(display_name__icontains=search) | Q(
                agent_skills__display_name__icontains=search
            )
            agents = agents.filter(query_filter).distinct('uuid')

        serializer = AgentSerializer(agents, many=True, context={"project_uuid": project_uuid})
        return Response(serializer.data)


class VtexAppOfficialAgentsView(APIView):
    permission_classes = [InternalCommunicationPermission]

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
        data = {
            "manager": {
                "external_id": team.external_id
            },
            "agents": serializer.data
        }
        return Response(data)


class VTexAppTeamView(APIView):

    permission_classes = [InternalCommunicationPermission]
    serializer_class = ActiveAgentTeamSerializer

    def get(self, request, *args, **kwargs):

        project_uuid = kwargs.get("project_uuid")

        team = Team.objects.get(project__uuid=project_uuid)
        team_agents = ActiveAgent.objects.filter(team=team)
        serializer = ActiveAgentTeamSerializer(team_agents, many=True)
        data = {
            "manager": {
                "external_id": team.external_id
            },
            "agents": serializer.data
        }
        return Response(data)


class ProjectCredentialsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        active_agents = ActiveAgent.objects.filter(team__project__uuid=project_uuid)
        active_agent_ids = active_agents.values_list('agent_id', flat=True)
        credentials = Credential.objects.filter(
            project__uuid=project_uuid,
            agents__in=active_agent_ids
        )

        official_credentials = credentials.filter(agents__is_official=True).distinct()
        custom_credentials = credentials.filter(agents__is_official=False).distinct()

        return Response({
            "official_agents_credentials": ProjectCredentialsListSerializer(official_credentials, many=True).data,
            "my_agents_credentials": ProjectCredentialsListSerializer(custom_credentials, many=True).data
        })

    def patch(self, request, project_uuid):
        credentials_data = request.data

        updated_credentials = []
        for key, value in credentials_data.items():
            try:
                credential = Credential.objects.get(project__uuid=project_uuid, key=key)
                credential.value = encrypt_value(value) if credential.is_confidential else value
                credential.save()
                updated_credentials.append(key)
            except Credential.DoesNotExist:
                continue

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

        created_credentials = []
        for cred_item in credentials_data:
            key = cred_item.get('name')
            if not key:
                continue

            value = cred_item.get('value')
            label = cred_item.get('label', key)
            placeholder = cred_item.get('placeholder')
            is_confidential = cred_item.get('is_confidential', True)

            treated_value = encrypt_value(value) if is_confidential else value

            credential, created = Credential.objects.get_or_create(
                project_id=project_uuid,
                key=key,
                defaults={
                    "label": label,
                    "is_confidential": is_confidential,
                    "placeholder": placeholder,
                    "value": treated_value
                }
            )

            if not created:
                credential.label = label
                credential.placeholder = placeholder
                credential.value = treated_value
                credential.is_confidential = is_confidential
                credential.save(update_fields=['label', 'is_confidential', 'placeholder', 'value'])

            credential.agents.add(agent)
            created_credentials.append(key)

        return Response({
            "message": "Credentials created successfully",
            "created_credentials": created_credentials
        })


class VtexAppProjectCredentialsView(APIView):

    permission_classes = [InternalCommunicationPermission]

    def get(self, request, project_uuid):
        active_agents = ActiveAgent.objects.filter(team__project__uuid=project_uuid)
        active_agent_ids = active_agents.values_list('agent_id', flat=True)
        credentials = Credential.objects.filter(
            project__uuid=project_uuid,
            agents__in=active_agent_ids
        )

        official_credentials = credentials.filter(agents__is_official=True).distinct()
        custom_credentials = credentials.filter(agents__is_official=False).distinct()

        return Response({
            "official_agents_credentials": ProjectCredentialsListSerializer(official_credentials, many=True).data,
            "my_agents_credentials": ProjectCredentialsListSerializer(custom_credentials, many=True).data
        })

    def patch(self, request, project_uuid):
        credentials_data = request.data

        updated_credentials = []
        for key, value in credentials_data.items():
            try:
                credential = Credential.objects.get(project__uuid=project_uuid, key=key)
                credential.value = encrypt_value(value) if credential.is_confidential else value
                credential.save()
                updated_credentials.append(key)
            except Credential.DoesNotExist:
                continue

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

        created_credentials = []
        for cred_item in credentials_data:
            key = cred_item.get('name')
            if not key:
                continue

            value = cred_item.get('value')
            label = cred_item.get('label', key)
            placeholder = cred_item.get('placeholder')
            is_confidential = cred_item.get('is_confidential', True)

            treated_value = encrypt_value(value) if is_confidential else value

            credential, created = Credential.objects.get_or_create(
                project_id=project_uuid,
                key=key,
                defaults={
                    "label": label,
                    "is_confidential": is_confidential,
                    "placeholder": placeholder,
                    "value": treated_value
                }
            )

            if not created:
                credential.label = label
                credential.placeholder = placeholder
                credential.value = treated_value
                credential.is_confidential = is_confidential
                credential.save(update_fields=['label', 'is_confidential', 'placeholder', 'value'])

            credential.agents.add(agent)
            created_credentials.append(key)

        return Response({
            "message": "Credentials created successfully",
            "created_credentials": created_credentials
        })
