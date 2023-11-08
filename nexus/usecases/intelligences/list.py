from nexus.intelligences.models import Intelligence
from nexus.usecases import orgs


class ListIntelligencesUseCases():

    def __init__(self):
        pass

    def get_org_intelligences(self, org_uuid: str):
        org = orgs.get_by_uuid(org_uuid)
        return Intelligence.objects.filter(org=org)
