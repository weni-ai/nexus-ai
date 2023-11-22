from nexus.intelligences.models import Intelligence, ContentBase
from nexus.usecases import orgs, users, intelligences


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


class CreateContentBaseUseCase():

    def create_contentbase(
            self,
            intelligence_uuid: str,
            user_email: str,
            title: str,
    ) -> ContentBase:

        user = users.get_by_email(user_email)
        intelligence = intelligences.get_by_intelligence_uuid(
            intelligence_uuid
        )
        contentbase = ContentBase.objects.create(
            title=title,
            intelligence=intelligence,
            created_by=user
        )
        return contentbase
