from nexus.orgs.models import Org, OrgAuth
from nexus.usecases.orgs.exceptions import OrgAuthDoesNotExists
from nexus.users.models import User


class GetOrgAuthUseCase:
    def get_org_auth_by_user(self, user: User, org: Org):
        try:
            return OrgAuth.objects.get(user=user, org=org)
        except OrgAuth.DoesNotExist as e:
            raise OrgAuthDoesNotExists from e
