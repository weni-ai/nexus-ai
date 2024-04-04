from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    IntegratedIntelligence,
    ContentBaseLink,
    LLM,
    ContentBaseAgent,
)
from nexus.usecases.intelligences.intelligences_dto import (
    ContentBaseFileDTO,
    ContentBaseDTO,
    ContentBaseTextDTO,
    ContentBaseLinkDTO,
    LLMDTO,
)
from nexus.usecases import (
    orgs,
    users,
    intelligences,
    projects
)
from nexus.orgs import permissions
from .exceptions import IntelligencePermissionDenied


class CreateIntelligencesUseCase():

    def create_intelligences(
            self,
            org_uuid: str,
            user_email: str,
            name: str,
            description: str = None
    ):
        org = orgs.get_by_uuid(org_uuid)
        user = users.get_by_email(user_email)

        has_permission = permissions.can_create_intelligence_in_org(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = Intelligence.objects.create(
            name=name, description=description,
            org=org, created_by=user
        )
        return intelligence


class CreateContentBaseUseCase():

    def create_contentbase(
            self,
            intelligence_uuid: str,
            user_email: str,
            title: str,
            description: str = None,
            language: str = 'pt-br',
            is_router: bool = False
    ) -> ContentBase:

        org_usecase = orgs.GetOrgByIntelligenceUseCase()
        org = org_usecase.get_org_by_intelligence_uuid(intelligence_uuid)
        user = users.get_by_email(user_email)

        has_permission = permissions.can_create_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = intelligences.get_by_intelligence_uuid(
            intelligence_uuid
        )
        contentbase = ContentBase.objects.create(
            title=title,
            intelligence=intelligence,
            created_by=user,
            description=description,
            language=language,
            is_router=is_router
        )
        ContentBaseAgent.objects.create(content_base=contentbase)
        intelligence.increase_content_bases_count()
        return contentbase


class CreateContentBaseTextUseCase():

    def create_contentbasetext(
            self,
            content_base_dto: ContentBaseDTO,
            content_base_text_dto: ContentBaseTextDTO,
    ) -> ContentBaseText:

        org_usecase = orgs.GetOrgByIntelligenceUseCase()
        org = org_usecase.get_org_by_contentbase_uuid(content_base_dto.uuid)
        user = users.get_by_email(content_base_dto.created_by_email)

        has_permission = permissions.can_create_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = intelligences.get_by_contentbase_uuid(
            content_base_dto.uuid
        )
        contentbasetext = ContentBaseText.objects.create(
            text=content_base_text_dto.text,
            content_base=contentbase,
            created_by=user,
            file=content_base_text_dto.file,
            file_name=content_base_text_dto.file_name
        )
        return contentbasetext


class CreateContentBaseFileUseCase():

    def create_content_base_file(self, content_base_file: ContentBaseFileDTO) -> ContentBaseFile:
        user = users.get_by_email(content_base_file.user_email)
        content_base = intelligences.get_by_contentbase_uuid(contentbase_uuid=content_base_file.content_base_uuid)
        content_base_file = ContentBaseFile.objects.create(
            file_name=content_base_file.file_name,
            file=content_base_file.file_url,
            extension_file=content_base_file.extension_file,
            content_base=content_base,
            created_by=user
        )
        return content_base_file


def create_integrated_intelligence(
    intelligence_uuid: str,
    user_email: str,
    project_uuid: str,
) -> IntegratedIntelligence:

    intelligence = intelligences.get_by_intelligence_uuid(intelligence_uuid)
    org = intelligence.org
    project_usecase = projects.ProjectsUseCase()
    project = project_usecase.get_by_uuid(project_uuid)

    user = users.get_by_email(user_email)
    has_permission = permissions.can_create_intelligence_in_org(user, org)
    if not has_permission:
        raise IntelligencePermissionDenied()

    integrated_intelligence = IntegratedIntelligence.objects.create(
        intelligence=intelligence,
        project=project,
        created_by=user
    )
    return integrated_intelligence


class CreateContentBaseLinkUseCase():
    def create_content_base_link(self, content_base_link: ContentBaseLinkDTO) -> ContentBaseLink:
        user = users.get_by_email(content_base_link.user_email)
        content_base = intelligences.get_by_contentbase_uuid(contentbase_uuid=content_base_link.content_base_uuid)
        content_base_link = ContentBaseLink.objects.create(
            link=content_base_link.link,
            content_base=content_base,
            created_by=user
        )
        return content_base_link


def create_llm(
    llm_dto: LLMDTO,
) -> LLM:
    usecase = projects.ProjectsUseCase()
    project = usecase.get_by_uuid(llm_dto.project_uuid)

    org = project.org
    user = users.get_by_email(llm_dto.user_email)

    has_permission = permissions.can_create_intelligence_in_org(user, org)
    if not has_permission:
        raise IntelligencePermissionDenied()

    intelligence = intelligences.get_integrated_intelligence_by_project(
        project_uuid=llm_dto.project_uuid
    )
    llm = LLM.objects.create(
        created_by=user,
        integrated_intelligence=intelligence,
        model=llm_dto.model,
        setup=llm_dto.setup,
        advanced_options=llm_dto.advanced_options
    )
    return llm
