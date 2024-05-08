from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
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
from nexus.usecases.event_driven.recent_activities import intelligence_activity_message
from django.conf import settings


class ProjectsUseCase:

    def __init__(
        self,
        intelligence_activity_message=intelligence_activity_message
    ) -> None:
        self.intelligence_activity_message = intelligence_activity_message

    def get_by_uuid(self, project_uuid: str) -> Project:
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise Exception(f"[ ProjectsUseCase ] Project with uuid `{project_uuid}` does not exists!")
        except Exception as exception:
            raise Exception(f"[ ProjectsUseCase ] error: {str(exception)}")

    def create_brain_project_base(
        self,
        project_dto,
        user_email: str,
        project: Project
    ) -> None:
        usecase = CreateIntelligencesUseCase(intelligence_activity_message=self.intelligence_activity_message)
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
            intelligence_activity_message=self.intelligence_activity_message
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
                "version": settings.WENIGPT_FINE_TUNNING_DEFAULT_VERSION,
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
            created_by=user
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

        return project
