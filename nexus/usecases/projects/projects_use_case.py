from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.users.get_by_email import get_by_email
from nexus.usecases.template_type.template_type_usecase import TemplateTypeUseCase
from nexus.usecases.intelligences.create import (
    CreateIntelligencesUseCase,
    CreateContentBaseUseCase,
    create_integrated_intelligence
)
from nexus.usecases import orgs


class ProjectsUseCase:

    def get_by_uuid(self, project_uuid: str) -> Project:
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise Exception(f"[ ProjectsUseCase ] Project with uuid `{project_uuid}` does not exists!")
        except Exception as exception:
            raise Exception(f"[ ProjectsUseCase ] error: {str(exception)}")

    def create_project(self, project_dto: ProjectCreationDTO, user_email: str) -> Project:
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

        usecase = CreateIntelligencesUseCase()
        base_intelligence = usecase.create_intelligences(
            org_uuid=project_dto.org_uuid,
            user_email=user_email,
            name=project_dto.name,
        )

        create_integrated_intelligence(
            intelligence_uuid=base_intelligence.uuid,
            project_uuid=project.uuid
        )

        usecase = CreateContentBaseUseCase()
        usecase.create_contentbase(
            intelligence_uuid=base_intelligence.uuid,
            user_email=user_email,
            title=project_dto.name,
            is_router=True
        )

        return project
