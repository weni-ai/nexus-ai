from nexus.orgs.models import Org, Role
from nexus.usecases import users
from .create_org_auth import create_org_auth


class CreateOrgUseCase:
    def create_orgs(self, user_email: str, name: str):
        user = users.get_by_email(user_email)
        org = Org.objects.create(created_by=user, name=name)

        create_org_auth(org, user, role=Role.ADMIN.value)

        return org
