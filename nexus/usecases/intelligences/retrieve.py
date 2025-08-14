from typing import Dict
import datetime

from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid,
    get_by_content_base_file_uuid,
    get_default_content_base_by_project,
    get_by_content_base_link_uuid,
)
from nexus.usecases import orgs, users, projects
from nexus.orgs import permissions
from .exceptions import (
    IntelligencePermissionDenied,
    ContentBaseTextDoesNotExist,
    ContentBaseFileDoesNotExist,
    ContentBaseLinkDoesNotExist,
)
from nexus.projects.permissions import has_project_permission
from nexus.intelligences.models import ContentBaseLink, Conversation
from nexus.projects.models import Project


class RetrieveIntelligenceUseCase():

    def get_intelligence(
            self,
            intelligence_uuid: str,
            user_email: str
    ):
        user = users.get_by_email(user_email)
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_intelligence_uuid(intelligence_uuid)

        has_permission = permissions.can_list_org_intelligences(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        return get_by_intelligence_uuid(intelligence_uuid)


class RetrieveContentBaseUseCase():

    def get_contentbase(
            self,
            contentbase_uuid: str,
            user_email: str
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        has_permission = permissions.can_list_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        return get_by_contentbase_uuid(contentbase_uuid)

    def get_default_by_project(
            self,
            project_uuid: str,
            user_email: str,
            is_superuser: bool = False,
    ):
        project = projects.get_project_by_uuid(project_uuid)

        if not is_superuser:
            user = users.get_by_email(user_email)
            has_project_permission(
                user=user,
                project=project,
                method='GET'
            )

        return get_default_content_base_by_project(project_uuid)


class RetrieveContentBaseTextUseCase():

    def get_contentbasetext(
        self,
        contentbasetext_uuid: str,
        user_email: str
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbasetext_uuid(
            contentbasetext_uuid
        )

        has_permission = permissions.can_list_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()
        return get_by_contentbasetext_uuid(contentbasetext_uuid)


class RetrieveContentBaseFileUseCase():

    def get_contentbasefile(self, contentbasefile_uuid: str, user_email: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)

        org = org_use_case.get_org_by_contentbasefile_uuid(
            contentbasefile_uuid
        )
        has_permission = permissions.can_list_content_bases(user, org)

        if not has_permission:
            raise IntelligencePermissionDenied()
        return get_by_content_base_file_uuid(contentbasefile_uuid)

    def get_inline_contentbase_file(self, contentbasefile_uuid: str):
        return get_by_content_base_file_uuid(contentbasefile_uuid)


class RetrieveContentBaseLinkUseCase():

    def get_contentbaselink(self, contentbaselink_uuid: str, user_email: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)

        org = org_use_case.get_org_by_contentbaselink_uuid(
            contentbaselink_uuid
        )
        has_permission = permissions.can_list_content_bases(user, org)

        if not has_permission:
            raise IntelligencePermissionDenied()
        return get_by_content_base_link_uuid(contentbaselink_uuid)

    def get_content_base_link_by_link(self, link: str, content_base_uuid: str):

        links = ContentBaseLink.objects.filter(
            link=link,
            content_base__uuid=content_base_uuid
        )

        if not links.exists():
            raise ContentBaseLink.DoesNotExist()

        return links


def get_file_info(file_uuid: str) -> Dict:
    try:
        file = get_by_content_base_file_uuid(file_uuid)
        return {
            "filename": file.file_name,
            "uuid": str(file.uuid),
            "created_file_name": file.created_file_name,
            "extension_file": file.extension_file,
        }
    except ContentBaseFileDoesNotExist:
        try:
            text = get_by_contentbasetext_uuid(file_uuid)
            return {
                "uuid": str(text.uuid),
                "created_file_name": ".text"
            }
        except ContentBaseTextDoesNotExist:
            try:
                link = get_by_content_base_link_uuid(file_uuid)
                return {
                    "uuid": str(link.uuid),
                    "created_file_name": f".link:{link.link}"
                }
            except ContentBaseLinkDoesNotExist:
                return {}


def get_conversation_object(
    project_uuid: str,
    contact_urn: str,
    start_date: datetime,
    end_date: datetime
) -> Conversation:
    project = Project.objects.get(uuid=project_uuid)
    return Conversation.objects.get(
        project=project,
        contact_urn=contact_urn,
        start_date__gte=start_date,
        end_date__lte=end_date
    )
