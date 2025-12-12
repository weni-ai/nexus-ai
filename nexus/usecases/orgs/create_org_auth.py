import logging

from nexus.orgs.models import Org, OrgAuth, Role
from nexus.orgs.org_dto import OrgAuthCreationDTO
from nexus.usecases import orgs, users
from nexus.users.models import User

from .exceptions import OrgRoleDoesNotExists


def _create_org_auth(org: Org, user: User, role: int):
    if not Role.has_value(role):
        raise OrgRoleDoesNotExists()
    try:
        org_auth = OrgAuth.objects.get(org=org, user=user)
        if org_auth.role < role:
            org_auth.role = role
            org_auth.save(update_fields=["role"])
    except Exception as exception:
        org_auth = OrgAuth.objects.create(org=org, user=user, role=role)
        logging.getLogger(__name__).error("[CreateOrgAuthUseCase] error: %s", exception, exc_info=True)
    return OrgAuth.objects.get(org=org, user=user)


class CreateOrgAuthUseCase:
    def create_org_auth(self, org_uuid: str, user_email: str, role: int):
        user = users.get_by_email(user_email)
        org = orgs.get_by_uuid(org_uuid)
        return _create_org_auth(org, user, role)

    def create_org_auth_with_dto(self, org_auth_dto: OrgAuthCreationDTO):
        user = users.get_by_email(user_email=org_auth_dto.user_email)
        org = orgs.get_by_uuid(org_uuid=org_auth_dto.org_uuid)
        return _create_org_auth(org=org, user=user, role=org_auth_dto.role)
