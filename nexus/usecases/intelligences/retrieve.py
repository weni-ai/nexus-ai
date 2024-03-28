from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid,
    get_by_content_base_file_uuid,
    get_by_content_base_link_uuid,
)
from nexus.usecases import orgs, users
from nexus.orgs import permissions
from .exceptions import IntelligencePermissionDenied


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
