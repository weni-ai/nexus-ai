from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile
)
from nexus.usecases import orgs
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid,
)


class ListIntelligencesUseCase():

    def get_org_intelligences(self, org_uuid: str):
        org = orgs.get_by_uuid(org_uuid)
        return Intelligence.objects.filter(org=org)


class ListContentBaseUseCase():

    def get_intelligence_contentbases(self, intelligence_uuid: str):
        intelligence = get_by_intelligence_uuid(intelligence_uuid)
        return ContentBase.objects.filter(intelligence=intelligence)


class ListContentBaseTextUseCase():

    def get_contentbase_contentbasetexts(self, contentbase_uuid: str):
        contentbase = get_by_contentbase_uuid(contentbase_uuid)
        return ContentBaseText.objects.filter(content_base=contentbase)


class ListContentBaseFileUseCase():

    def get_contentbase_file(self, contentbase_uuid: str):
        contentbase = get_by_contentbase_uuid(contentbase_uuid=contentbase_uuid)
        return ContentBaseFile.objects.filter(contentbase=contentbase)


class ListAllIntelligenceContentUseCase():

    def get_project_intelligences(self, project_uuid: str):
        project_usecase = ProjectsUseCase()
        response = []
        project = project_usecase.get_by_uuid(project_uuid)
        intelligences = ListIntelligencesUseCase().get_org_intelligences(project.org.uuid)
        for intelligence in intelligences:
            cur_data = {"intelligence_name": intelligence.name, "content_bases": []}
            content_bases = ListContentBaseUseCase().get_intelligence_contentbases(intelligence_uuid=str(intelligence.uuid))
            for content_base in content_bases:
                cur_data["content_bases"].append({"uuid": str(content_base.uuid), "content_base_name": content_base.title})
            response.append(cur_data)
        return response
