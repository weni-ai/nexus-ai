from nexus.orgs.models import Org, OrgAuth, Role
from nexus.usecases.users.exceptions import UserDoesNotExists
from nexus.users.models import User

from .exceptions import OrgDoesNotExists, OrgRoleDoesNotExists


def create_org_auth(org_uuid: str, user_email: str, role: int):
    try:
        org = Org.objects.get(uuid=org_uuid)
    except (Org.DoesNotExist):
        raise OrgDoesNotExists()

    try:
        user = User.objects.get(email=user_email)
    except User.DoesNotExist:
        raise UserDoesNotExists()

    if Role.has_value(role):
        return OrgAuth.objects.create(org=org, user=user, role=role)

    raise OrgRoleDoesNotExists()
