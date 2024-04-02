from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid,
    get_by_content_base_file_uuid,
    get_llm_by_project_uuid,
)
from nexus.usecases import orgs, users, projects
from nexus.orgs import permissions
from .exceptions import IntelligencePermissionDenied
from nexus.usecases.intelligences.intelligences_dto import UpdateContentBaseFileDTO, UpdateLLMDTO
from nexus.intelligences.models import ContentBase


class UpdateIntelligenceUseCase():

    def update_intelligences(
            self,
            intelligence_uuid: str,
            user_email: str,
            name: str = None,
            description: str = None,
    ):
        user = users.get_by_email(user_email)
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_intelligence_uuid(intelligence_uuid)

        has_permission = permissions.can_edit_intelligence_of_org(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = get_by_intelligence_uuid(intelligence_uuid)

        if name:
            intelligence.name = name

        if description:
            intelligence.description = description

        intelligence.save()

        return intelligence


class UpdateContentBaseUseCase():

    def update_contentbase(
            self,
            contentbase_uuid: str,
            user_email: str,
            title: str = None,
            language: str = None,
            description: str = None,
    ) -> ContentBase:
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        has_permission = permissions.can_edit_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = get_by_contentbase_uuid(contentbase_uuid)

        update_fields = []
        if title:
            contentbase.title = title
            update_fields.append('title')

        if language:
            contentbase.language = language
            update_fields.append('language')

        if description:
            contentbase.description = description
            update_fields.append('description')

        contentbase.save(update_fields=update_fields)

        return contentbase


class UpdateContentBaseTextUseCase():

    def update_contentbasetext(
            self,
            contentbasetext_uuid: str,
            user_email: str,
            text: str = None,
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbasetext_uuid(
            contentbasetext_uuid
        )

        has_permission = permissions.can_edit_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbasetext = get_by_contentbasetext_uuid(contentbasetext_uuid)

        if text:
            contentbasetext.text = text
            contentbasetext.save(update_fields=['text'])

        return contentbasetext


class UpdateContentBaseFileUseCase():

    def update_content_base_file(
            self,
            content_base_file_uuid: str,
            user_email: str,
            update_content_base_file_dto: UpdateContentBaseFileDTO
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbasefile_uuid(
            content_base_file_uuid
        )

        has_permission = permissions.can_edit_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        content_base_file = get_by_content_base_file_uuid(content_base_file_uuid)

        for attr, value in update_content_base_file_dto.dict().items():
            setattr(content_base_file, attr, value)
        content_base_file.save()

        return content_base_file


def update_llm_by_project(
    update_llm_dto: UpdateLLMDTO
):
    project_usecase = projects.ProjectsUseCase()
    project = project_usecase.get_by_uuid(update_llm_dto.project_uuid)
    org = project.org
    user = users.get_by_email(update_llm_dto.user_email)

    has_permission = permissions.can_edit_intelligence_of_org(user, org)
    if not has_permission:
        raise IntelligencePermissionDenied()

    llm = get_llm_by_project_uuid(project.uuid)

    for attr, value in update_llm_dto.dict().items():
        setattr(llm, attr, value)
    llm.save()

    return llm
