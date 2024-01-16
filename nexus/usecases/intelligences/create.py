from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile
)
from nexus.usecases import orgs, users, intelligences
from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
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
            created_by=user
        )
        return contentbase


class CreateContentBaseTextUseCase():

    def create_contentbasetext(
            self,
            contentbase_uuid: str,
            user_email: str,
            text: str,
    ) -> ContentBaseText:

        org_usecase = orgs.GetOrgByIntelligenceUseCase()
        org = org_usecase.get_org_by_contentbase_uuid(contentbase_uuid)
        user = users.get_by_email(user_email)

        has_permission = permissions.can_create_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = intelligences.get_by_contentbase_uuid(
            contentbase_uuid
        )
        contentbasetext = ContentBaseText.objects.create(
            text=text,
            content_base=contentbase,
            created_by=user,
        )
        return contentbasetext

class CreateContentBaseFileUseCase():

    def create_content_base_file(self, content_base_file: ContentBaseFileDTO) -> ContentBaseFile:
        user = users.get_by_email(content_base_file.user_email)
        content_base = intelligences.get_by_contentbase_uuid(contentbase_uuid=content_base_file.content_base_uuid)
        content_base_file = ContentBaseFile.objects.create(
            file=content_base_file.file_url,
            extension_file=content_base_file.extension_file,
            content_base=content_base,
            created_by=user
        )
        return content_base_file
