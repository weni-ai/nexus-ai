from nexus.usecases import orgs, users
from nexus.orgs.models import Org, OrgAuth, Role
from nexus.users.models import User
from .exceptions import OrgRoleDoesNotExists


def _create_org_auth(org: Org, user: User, role: int):
    if not Role.has_value(role):
        raise OrgRoleDoesNotExists()

    return OrgAuth.objects.create(org=org, user=user, role=role)


class CreateOrgAuthUseCase:
    def create_org_auth(self, org_uuid: str, user_email: str, role: int):
        user = users.get_by_email(user_email)
        org = orgs.get_by_uuid(org_uuid)

        return _create_org_auth(org, user, role)
