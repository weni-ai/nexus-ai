from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile
)
from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO, ContentBaseDTO, ContentBaseTextDTO
from nexus.usecases import (
    orgs,
    users,
    intelligences
)
from nexus.orgs import permissions
from .exceptions import IntelligencePermissionDenied


class CreateIntelligencesUseCase():

    def create_intelligences(
            self,
            org_uuid: str,
            user_email: str,
            name: str,
            description: str
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
            description: str,
            language: str = 'pt-br'
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
            language=language
        )
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
