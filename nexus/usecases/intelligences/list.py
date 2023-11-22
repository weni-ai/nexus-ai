from nexus.intelligences.models import Intelligence, ContentBase
from nexus.usecases import orgs
from .get_by_uuid import get_by_intelligence_uuid


class ListIntelligencesUseCase():

    def __init__(self):
        pass

    def get_org_intelligences(self, org_uuid: str):
        org = orgs.get_by_uuid(org_uuid)
        return Intelligence.objects.filter(org=org)


class ListContentBaseUseCase():

    def __init__(self):
        pass

    def get_intelligence_contentbases(self, intelligence_uuid: str):
        intelligence = get_by_intelligence_uuid(intelligence_uuid)
        return ContentBase.objects.filter(intelligence=intelligence)
