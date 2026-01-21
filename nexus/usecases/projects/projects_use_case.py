import json

import pendulum
import sentry_sdk
from django.conf import settings

from nexus.events import event_manager, notify_async
from nexus.inline_agents.models import ContactField
from nexus.intelligences.models import ContentBase, IntegratedIntelligence
from nexus.projects.exceptions import ProjectDoesNotExist
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.usecases import orgs
from nexus.usecases.agents import AgentUsecase
from nexus.usecases.intelligences.create import (
    CreateContentBaseUseCase,
    CreateIntelligencesUseCase,
    create_integrated_intelligence,
    create_llm,
)
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.intelligences_dto import LLMDTO
from nexus.usecases.users.get_by_email import get_by_email

from .create import ProjectAuthUseCase


class ProjectsUseCase:
    def __init__(
        self,
        event_manager_notify=event_manager.notify,
        external_agent_client=BedrockFileDatabase,
    ) -> None:
        self.event_manager_notify = event_manager_notify
        self.external_agent_client = external_agent_client

    def get_by_uuid(self, project_uuid: str) -> Project:
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist as e:
            raise ProjectDoesNotExist(f"[ ProjectsUseCase ] Project with uuid `{project_uuid}` does not exists!") from e
        except Exception as exception:
            raise Exception(f"[ ProjectsUseCase ] error: {str(exception)}") from exception

    def create_multi_agents_base(
        self,
        project_uuid: str,
        supervisor_name: str,
        supervisor_description: str,
        supervisor_instructions: str,
        user,
    ):
        agents_usecase = AgentUsecase(self.external_agent_client)
        team = agents_usecase.create_supervisor(
            project_uuid=project_uuid,
            supervisor_name=supervisor_name,
            supervisor_description=supervisor_description,
            supervisor_instructions=supervisor_instructions,
            is_single_agent=True,
        )

        alias_name = f"{supervisor_name}-multi-agent"
        (
            supervisor_agent_alias_id,
            supervisor_agent_alias_arn,
            supervisor_alias_version,
        ) = agents_usecase.external_agent_client.create_agent_alias(alias_name=alias_name, agent_id=team.external_id)
        team.versions.create(
            alias_id=supervisor_agent_alias_id,
            alias_name=alias_name,
            metadata={
                "supervisor_alias_arn": supervisor_agent_alias_arn,
                "supervisor_alias_version": supervisor_alias_version,
            },
            created_by=user,
        )
        return team

    def create_brain_project_base(self, project_dto, user_email: str, project: Project) -> None:
        usecase = CreateIntelligencesUseCase(event_manager_notify=self.event_manager_notify)
        base_intelligence = usecase.create_intelligences(
            org_uuid=project_dto.org_uuid, user_email=user_email, name=project_dto.name, is_router=True
        )

        create_integrated_intelligence(
            intelligence_uuid=base_intelligence.uuid, project_uuid=project.uuid, user_email=user_email
        )
        usecase = CreateContentBaseUseCase(
            event_manager_notify=self.event_manager_notify,
        )
        usecase.create_contentbase(
            intelligence_uuid=base_intelligence.uuid, user_email=user_email, title=project_dto.name, is_router=True
        )

        llm_dto = LLMDTO(
            user_email=user_email,
            project_uuid=project.uuid,
            setup={
                "version": settings.WENIGPT_DEFAULT_VERSION,
                "temperature": settings.WENIGPT_TEMPERATURE,
                "top_p": settings.WENIGPT_TOP_P,
                "top_k": settings.WENIGPT_TOP_K,
                "max_length": settings.WENIGPT_MAX_LENGHT,
            },
        )
        create_llm(llm_dto=llm_dto)

    def create_project(self, project_dto: ProjectCreationDTO, user_email: str) -> Project:
        user = get_by_email(user_email=user_email)
        org = orgs.get_by_uuid(org_uuid=project_dto.org_uuid)

        backend = "OpenAIBackend"

        template_type = None
        if project_dto.is_template:
            from nexus.usecases.template_type.template_type_usecase import TemplateTypeUseCase

            template_type = TemplateTypeUseCase().get_by_uuid(project_dto.template_type_uuid)
        project = Project.objects.create(
            uuid=project_dto.uuid,
            name=project_dto.name,
            org=org,
            template_type=template_type,
            is_template=project_dto.is_template,
            created_by=user,
            brain_on=project_dto.brain_on,
            indexer_database=project_dto.indexer_database,
            agents_backend=backend,
        )

        self.create_brain_project_base(project_dto=project_dto, user_email=user_email, project=project)

        if project.brain_on and project.agents_backend == "BedrockBackend":
            sentry_sdk.set_tag("bedrock_supervisor_provisioned", True)
            sentry_sdk.set_context(
                "bedrock_provisioning",
                {
                    "project_uuid": str(project.uuid),
                    "agents_backend": project.agents_backend,
                },
            )
            sentry_sdk.capture_message("Provisioning Bedrock supervisor on project creation", level="info")
            supervisor_name = f"Supervisor for {project.name}"
            supervisor_description = "Default supervisor description."
            supervisor_instructions = "Default supervisor instructions."

            self.create_multi_agents_base(
                project_uuid=str(project.uuid),
                supervisor_name=supervisor_name,
                supervisor_description=supervisor_description,
                supervisor_instructions=supervisor_instructions,
                user=user,
            )
        auths = project_dto.authorizations
        auth_usecase = ProjectAuthUseCase()
        for auth in auths:
            auth_consumer_msg = {"role": auth.get("role"), "user": auth.get("user_email"), "project": project.uuid}
            auth_usecase.create_project_auth(consumer_msg=auth_consumer_msg)

        return project

    def get_indexer_database_by_uuid(self, project_uuid: str):
        project = self.get_by_uuid(project_uuid)
        return {Project.BEDROCK: BedrockFileDatabase, Project.SENTENX: SentenXFileDataBase}.get(
            project.indexer_database
        )

    def get_indexer_database_by_project(self, project: Project):
        """It's the same method as "get_indexer_database_by_uuid" but skips retrieving the project from the DB"""
        return {Project.BEDROCK: BedrockFileDatabase, Project.SENTENX: SentenXFileDataBase}.get(
            project.indexer_database
        )

    def get_project_by_content_base_uuid(self, content_base_uuid: str) -> Project:
        content_base = ContentBase.objects.get(uuid=content_base_uuid)
        intelligence = content_base.intelligence
        project = IntegratedIntelligence.objects.get(intelligence=intelligence).project
        return project

    def set_project_prompt_creation_configurations(
        self,
        project_uuid: str,
        use_prompt_creation_configurations: bool,
        conversation_turns_to_include: int,
        exclude_previous_thinking_steps: bool,
    ) -> dict:
        project = self.get_by_uuid(project_uuid)
        project.use_prompt_creation_configurations = use_prompt_creation_configurations
        project.conversation_turns_to_include = conversation_turns_to_include
        project.exclude_previous_thinking_steps = exclude_previous_thinking_steps
        project.save()
        project.refresh_from_db()
        return {
            "use_prompt_creation_configurations": project.use_prompt_creation_configurations,
            "conversation_turns_to_include": project.conversation_turns_to_include,
            "exclude_previous_thinking_steps": project.exclude_previous_thinking_steps,
        }

    def get_project_prompt_creation_configurations(self, project_uuid: str) -> dict:
        project = self.get_by_uuid(project_uuid)
        return {
            "use_prompt_creation_configurations": project.use_prompt_creation_configurations,
            "conversation_turns_to_include": project.conversation_turns_to_include,
            "exclude_previous_thinking_steps": project.exclude_previous_thinking_steps,
        }

    def get_agents_backend_by_project(self, project_uuid: str) -> str:
        project = self.get_by_uuid(project_uuid)
        return project.agents_backend

    def set_agents_backend_by_project(self, project_uuid: str, agents_backend: str) -> None:
        backends = {"openai": "OpenAIBackend", "bedrock": "BedrockBackend"}
        agents_backend: str | None = backends.get(agents_backend.lower())

        if not agents_backend:
            raise Exception(f"[ ProjectsUseCase ] Invalid backend: {agents_backend}")

        project = self.get_by_uuid(project_uuid)
        project.agents_backend = agents_backend
        project.save()

        # Fire cache invalidation event for project update (async observer)
        notify_async(
            event="cache_invalidation:project",
            project=project,
        )

        return project.agents_backend

    def get_agent_builder_project_details(self, project_uuid: str) -> dict:
        # TODO: Organize code, remove instruction formatting from this class
        from inline_agents.backends import BackendsRegistry  # to avoid circular import

        try:
            project = self._get_project_with_optimized_queries(project_uuid)

            if not project.inline_agent_switch:
                return {
                    "indexed_database": project.indexer_database,
                }

            content_base = get_default_content_base_by_project(project_uuid)
            backend = BackendsRegistry.get_backend(project.agents_backend)

            supervisor_data = self._get_supervisor_data(project, backend)
            contact_fields_json = self._build_contact_fields_json(project)
            integrated_agents_data = self._get_integrated_agents_data(project)
            formatted_instruction = self._format_supervisor_instruction(
                backend, supervisor_data, content_base, contact_fields_json, project_uuid
            )

            return {
                "agents_backend": project.agents_backend,
                "manager_foundation_model": supervisor_data["foundation_model"],
                "integrated_agents": integrated_agents_data,
                "instruction_character_count": len(formatted_instruction),
            }

        except Exception as e:
            raise Exception(f"Error getting agent builder project details: {str(e)}") from e

    def _get_project_with_optimized_queries(self, project_uuid: str) -> Project:
        return Project.objects.select_related().prefetch_related("integrated_agents__agent").get(uuid=project_uuid)

    def _get_supervisor_data(self, project: Project, backend) -> dict:
        foundation_model = project.default_supervisor_foundation_model
        if project.agents_backend == "BedrockBackend":
            return backend.supervisor_repository.get_supervisor(project, foundation_model)
        else:
            return backend.get_supervisor(
                use_components=project.use_components,
                human_support=project.human_support,
                default_supervisor_foundation_model=foundation_model,
                supervisor_agent_uuid=project.manager_agent.uuid if project.manager_agent else None,
            )

    def _build_contact_fields_json(self, project: Project) -> str:
        contact_fields = ContactField.objects.filter(project=project).values("key", "value_type")

        contact_fields_dict = {field["key"]: {"type": field["value_type"], "value": None} for field in contact_fields}

        return json.dumps(contact_fields_dict)

    def _get_integrated_agents_data(self, project: Project) -> list[dict]:
        integrated_agents = project.integrated_agents.select_related("agent").all()

        return [
            {
                "name": integrated_agent.agent.name,
                "slug": integrated_agent.agent.slug,
                "foundation_model": integrated_agent.agent.current_foundation_model(project.agents_backend, project),
            }
            for integrated_agent in integrated_agents
        ]

    def _format_supervisor_instruction(
        self, backend, supervisor_data: dict, content_base: ContentBase, contact_fields_json: str, project_uuid: str
    ) -> str:
        time_now = pendulum.now("America/Sao_Paulo")
        llm_formatted_time = f"Today is {time_now.format('dddd, MMMM D, YYYY [at] HH:mm:ss z')}"

        supervisor_instructions = content_base.instructions.values_list("instruction", flat=True)
        supervisor_instructions_text = "\n".join(supervisor_instructions)

        agent_data = content_base.agent
        project = self.get_by_uuid(project_uuid)

        return backend.team_adapter._format_supervisor_instructions(
            instruction=supervisor_data["instruction"],
            date_time_now=llm_formatted_time,
            contact_fields=contact_fields_json,
            supervisor_name=agent_data.name,
            supervisor_role=agent_data.role,
            supervisor_goal=agent_data.goal,
            supervisor_adjective=agent_data.personality,
            supervisor_instructions=supervisor_instructions_text or "",
            business_rules=project.human_support_prompt or "",
            project_id=project_uuid,
            contact_id="",
            contact_name="",
            channel_uuid="",
        )
