from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    ContentBaseLink,
    LLM,
)
from nexus.usecases import orgs, users, projects
from nexus.orgs import permissions
from nexus.projects.permissions import has_project_permission
from .exceptions import IntelligencePermissionDenied
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
    get_integrated_intelligence_by_project
)


class ListIntelligencesUseCase():

    def get_org_intelligences(
        self,
        org_uuid: str,
        user_email: str = None,
        is_super_user: bool = False,
    ) -> Intelligence:
        org = orgs.get_by_uuid(org_uuid)

        if not is_super_user:
            user = users.get_by_email(user_email)
            has_permission = permissions.can_list_org_intelligences(user, org)
            if not has_permission:
                raise IntelligencePermissionDenied()

        return Intelligence.objects.filter(org=org)


class ListAllIntelligenceContentUseCase():

    def get_project_intelligences(
            self,
            project_uuid: str,
            user_email: str = None,
            is_super_user: bool = False
    ):
        project_usecase = ProjectsUseCase()
        response = []
        project = project_usecase.get_by_uuid(project_uuid)
        intelligences = ListIntelligencesUseCase().get_org_intelligences(
            project.org.uuid,
            user_email=user_email,
            is_super_user=is_super_user
        )
        for intelligence in intelligences:
            cur_data = {"intelligence_name": intelligence.name, "content_bases": []}
            content_bases = ListContentBaseUseCase().get_intelligence_contentbases(
                intelligence_uuid=str(intelligence.uuid),
                user_email=user_email,
                is_super_user=is_super_user
            )
            for content_base in content_bases:
                cur_data["content_bases"].append({"uuid": str(content_base.uuid), "content_base_name": content_base.title})
            response.append(cur_data)
        return response


class ListContentBaseUseCase():

    def get_intelligence_contentbases(
        self,
        intelligence_uuid: str,
        user_email: str = None,
        is_super_user: bool = False,
    ) -> ContentBase:
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_intelligence_uuid(intelligence_uuid)
        if not is_super_user:
            user = users.get_by_email(user_email)
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


class ListContentBaseFileUseCase():

    def get_contentbase_file(self, contentbase_uuid: str, user_email: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        user = users.get_by_email(user_email)

        has_permission = permissions.can_list_content_bases(user, org)
        if not has_permission:
            raise IntelligencePermissionDenied()

        content_base = get_by_contentbase_uuid(contentbase_uuid=contentbase_uuid)
        return ContentBaseFile.objects.filter(content_base=content_base)


class ListContentBaseLinkUseCase():
    def get_contentbase_link(self, contentbase_uuid: str, user_email: str):
        org_use_case = orgs.GetOrgByIntelligenceUseCase()
        org = org_use_case.get_org_by_contentbase_uuid(contentbase_uuid)

        user = users.get_by_email(user_email)

        has_permission = permissions.can_list_content_bases(user, org)

        if not has_permission:
            raise IntelligencePermissionDenied()

        content_base = get_by_contentbase_uuid(contentbase_uuid=contentbase_uuid)
        return ContentBaseLink.objects.filter(content_base=content_base)


def get_llm_config(
    project_uuid: str,
    user_email: str,
) -> LLM:
    integrated_intelligence = get_integrated_intelligence_by_project(project_uuid)
    user = users.get_by_email(user_email)
    project = projects.get_project_by_uuid(project_uuid)

    has_project_permission(
        user=user,
        project=project,
        method='GET'
    )

    return LLM.objects.filter(integrated_intelligence=integrated_intelligence).order_by('created_at').first()
