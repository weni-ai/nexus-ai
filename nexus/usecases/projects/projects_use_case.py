from django.conf import settings
from django.template.defaultfilters import slugify

from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.projects.exceptions import ProjectDoesNotExist

from nexus.usecases.agents import AgentUsecase
from nexus.usecases.intelligences.intelligences_dto import LLMDTO
from nexus.usecases.users.get_by_email import get_by_email
from nexus.usecases.template_type.template_type_usecase import TemplateTypeUseCase
from nexus.usecases.intelligences.create import (
    CreateIntelligencesUseCase,
    CreateContentBaseUseCase,
    create_integrated_intelligence,
    create_llm
)
from .create import ProjectAuthUseCase
from nexus.usecases import orgs
from nexus.events import event_manager
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.intelligences.models import ContentBase, IntegratedIntelligence


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
        except Project.DoesNotExist:
            raise ProjectDoesNotExist(f"[ ProjectsUseCase ] Project with uuid `{project_uuid}` does not exists!")
        except Exception as exception:
            raise Exception(f"[ ProjectsUseCase ] error: {str(exception)}")

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
            is_single_agent=True
        )

        alias_name = f"{supervisor_name}-multi-agent"
        supervisor_agent_alias_id, supervisor_agent_alias_arn, supervisor_alias_version = agents_usecase.external_agent_client.create_agent_alias(
            alias_name=alias_name, agent_id=team.external_id
        )
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

    def create_brain_project_base(
        self,
        project_dto,
        user_email: str,
        project: Project
    ) -> None:
        usecase = CreateIntelligencesUseCase(
            event_manager_notify=self.event_manager_notify
        )
        base_intelligence = usecase.create_intelligences(
            org_uuid=project_dto.org_uuid,
            user_email=user_email,
            name=project_dto.name,
        )

        create_integrated_intelligence(
            intelligence_uuid=base_intelligence.uuid,
            project_uuid=project.uuid,
            user_email=user_email
        )
        usecase = CreateContentBaseUseCase(
            event_manager_notify=self.event_manager_notify,
        )
        usecase.create_contentbase(
            intelligence_uuid=base_intelligence.uuid,
            user_email=user_email,
            title=project_dto.name,
            is_router=True
        )

        llm_dto = LLMDTO(
            user_email=user_email,
            project_uuid=project.uuid,
            setup={
                "version": settings.WENIGPT_DEFAULT_VERSION,
                'temperature': settings.WENIGPT_TEMPERATURE,
                'top_p': settings.WENIGPT_TOP_P,
                'top_k': settings.WENIGPT_TOP_K,
                'max_length': settings.WENIGPT_MAX_LENGHT,
            }
        )
        create_llm(llm_dto=llm_dto)

    def create_project(
        self,
        project_dto: ProjectCreationDTO,
        user_email: str
    ) -> Project:
        user = get_by_email(user_email=user_email)
        org = orgs.get_by_uuid(org_uuid=project_dto.org_uuid)
        template_type = None
        if project_dto.is_template:
            template_type = TemplateTypeUseCase().get_by_uuid(project_dto.template_type_uuid)
        project = Project.objects.create(
            uuid=project_dto.uuid,
            name=project_dto.name,
            org=org,
            template_type=template_type,
            is_template=project_dto.is_template,
            created_by=user,
            brain_on=project_dto.brain_on,
            indexer_database=project_dto.indexer_database
        )

        self.create_brain_project_base(
            project_dto=project_dto,
            user_email=user_email,
            project=project
        )

        auths = project_dto.authorizations
        auth_usecase = ProjectAuthUseCase()
        for auth in auths:
            auth_consumer_msg = {
                "role": auth.get("role"),
                "user": auth.get("user_email"),
                "project": project.uuid
            }
            auth_usecase.create_project_auth(
                consumer_msg=auth_consumer_msg
            )

        agent_valid_users = settings.AGENT_VALID_USERS
        agent_valid_orgs = settings.AGENT_VALID_ORGS

        if project.created_by.email in agent_valid_users or str(org.uuid) in agent_valid_orgs:
            project.inline_agent_switch = True
            project.save()

        return project

    def get_indexer_database_by_uuid(self, project_uuid: str):
        project = self.get_by_uuid(project_uuid)
        return {
            Project.BEDROCK: BedrockFileDatabase,
            Project.SENTENX: SentenXFileDataBase
        }.get(project.indexer_database)

    def get_indexer_database_by_project(self, project: Project):
        """It's the same method as "get_indexer_database_by_uuid" but skips retrieving the project from the DB"""
        return {
            Project.BEDROCK: BedrockFileDatabase,
            Project.SENTENX: SentenXFileDataBase
        }.get(project.indexer_database)

    def get_project_by_content_base_uuid(self, content_base_uuid: str) -> Project:
        content_base = ContentBase.objects.get(uuid=content_base_uuid)
        intelligence = content_base.intelligence
        project = IntegratedIntelligence.objects.get(intelligence=intelligence).project
        return project
