from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText
)
from nexus.usecases import orgs
from .get_by_uuid import (
    get_by_intelligence_uuid,
    get_by_contentbase_uuid
)


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


class ListContentBaseTextUseCase():

    def __init__(self):
        pass

    def get_contentbase_contentbasetexts(self, contentbase_uuid: str):
        contentbase = get_by_contentbase_uuid(contentbase_uuid)
        return ContentBaseText.objects.filter(contentbase=contentbase)
