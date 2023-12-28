from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText
)
from nexus.usecases import orgs, users
from nexus.orgs import permissions
from .exceptions import IntelligencePermissionDenied
from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid
)


class ListIntelligencesUseCase():

    def get_org_intelligences(
        self,
        org_uuid: str,
        user_email: str
    ) -> Intelligence:
        user = users.get_by_email(user_email)
        org = orgs.get_by_uuid(org_uuid)

        has_permission = permissions.can_list_org_intelligences(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()
        return Intelligence.objects.filter(org=org)


class ListContentBaseUseCase():

    def get_intelligence_contentbases(
        self,
        intelligence_uuid: str,
        user_email: str
    ) -> ContentBase:
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_intelligence_uuid(intelligence_uuid)

        has_permission = permissions.can_list_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        intelligence = get_by_intelligence_uuid(intelligence_uuid)
        return ContentBase.objects.filter(intelligence=intelligence)


class ListContentBaseTextUseCase():

    def get_contentbase_contentbasetexts(
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
        contentbase = get_by_contentbase_uuid(contentbase_uuid)
        return ContentBaseText.objects.filter(content_base=contentbase)
