from nexus.orgs.models import Org, Role
from nexus.usecases import users
from .create_org_auth import CreateOrgAuthUseCase
from nexus.orgs.org_dto import OrgCreationDTO


class CreateOrgUseCase:
    def create_orgs(self, user_email: str, org_dto: OrgCreationDTO):
        user = users.get_by_email(user_email)
        org = Org.objects.create(uuid=org_dto.uuid, created_by=user, name=org_dto.name)

        org_auth_usecase = CreateOrgAuthUseCase()

        org_auth_usecase.create_org_auth(
            org_uuid=str(org.uuid),
            user_email=user.email,
            role=Role.ADMIN.value
        )
        for authorization in org_dto.authorizations:
            org_auth_usecase.create_org_auth(
                org_uuid=org.uuid,
                user_email=authorization.get("user_email"),
                role=authorization.get("role")
            )

        return org
