from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_by_contentbasetext_uuid
)
from nexus.usecases import orgs, users
from nexus.orgs import permissions
from .exceptions import IntelligencePermissionDenied


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
    ):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        user = users.get_by_email(user_email)
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        has_permission = permissions.can_edit_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        contentbase = get_by_contentbase_uuid(contentbase_uuid)

        if title:
            contentbase.title = title
            contentbase.save(update_fields=['title'])

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
