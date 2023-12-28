from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid
)
from nexus.usecases import (
    users,
    orgs
)
from nexus.orgs import permissions
from .exceptions import IntelligencePermissionDenied


class DeleteIntelligenceUseCase():

    def delete_intelligences(
            self,
            intelligence_uuid: str,
            user_email: str
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_intelligence_uuid(intelligence_uuid)

        has_permission = permissions.can_delete_intelligence_of_org(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = get_by_intelligence_uuid(intelligence_uuid)
        intelligence.delete()
        return True


class DeleteContentBaseUseCase():

    def delete_contentbase(
            self,
            contentbase_uuid: str,
            user_email: str
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        has_permission = permissions.can_delete_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = get_by_contentbase_uuid(contentbase_uuid)
        contentbase.delete()
        return True


class DeleteContentBaseTextUseCase():

    def delete_contentbasetext(
            self,
            contentbasetext_uuid: str,
            user_email: str
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_contentbasetext_uuid(
            contentbasetext_uuid
        )
        user = users.get_by_email(user_email)

        has_permission = permissions.can_delete_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbasetext = get_by_contentbasetext_uuid(contentbasetext_uuid)
        contentbasetext.delete()
        return True
