from nexus.users.models import User
from nexus.orgs.models import Org, OrgAuth
from nexus.usecases.orgs.exceptions import OrgAuthDoesNotExists


class GetOrgAuthUseCase:
    def get_org_auth_by_user(self, user: User, org: Org):
        try:
            return OrgAuth.objects.get(user=user, org=org)
        except OrgAuth.DoesNotExist:
            raise OrgAuthDoesNotExists
