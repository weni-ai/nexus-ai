from nexus.intelligences.models import Intelligence
from nexus.usecases import orgs, users


class CreateIntelligencesUseCase():

    def __init__(self):
        pass

    def create_intelligences(
            self, org_uuid: str, user_email: str,
            name: str, description: str
    ):
        org = orgs.get_by_uuid(org_uuid)
        user = users.get_by_email(user_email)
        intelligence = Intelligence.objects.create(
            name=name, description=description,
            org=org, created_by=user
        )
        return intelligence
