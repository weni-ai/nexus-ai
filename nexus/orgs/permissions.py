from django.conf import settings

from nexus.orgs.models import Org, OrgAuth, Role
from nexus.usecases.orgs.exceptions import OrgAuthDoesNotExists
from nexus.usecases.orgs.get_org_auth import GetOrgAuthUseCase
from nexus.users.models import User


def get_user_auth(user: User, org: Org):
    return OrgAuth.objects.get(user=user, org=org)


def is_super_user(token: str):
    token = token.split("Bearer")[1].strip()
    return token in settings.EXTERNAL_SUPERUSERS_TOKENS


def is_admin(auth: OrgAuth) -> bool:
    return auth.role == Role.ADMIN.value


def can_contribute(auth: OrgAuth) -> bool:
    return auth.role >= Role.CONTRIBUTOR.value


def can_view(auth: OrgAuth) -> bool:
    return auth.role >= Role.VIEWER.value


def can_create_intelligence_in_org(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False


def can_list_org_intelligences(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_view(auth)
    except OrgAuthDoesNotExists:
        return False


def can_edit_intelligence_of_org(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False


def can_delete_intelligence_of_org(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return is_admin(auth)
    except OrgAuthDoesNotExists:
        return False


def can_list_content_bases(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_view(auth)
    except OrgAuthDoesNotExists:
        return False


def can_create_content_bases(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False


def can_delete_content_bases(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False


def can_edit_content_bases(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False


def can_add_content_base_file(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False


def can_delete_content_base_file(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False


def can_test_content_base(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False


def can_download_content_base_file(user: User, org: Org) -> bool:
    try:
        usecase = GetOrgAuthUseCase()
        auth = usecase.get_org_auth_by_user(user, org)
        return can_contribute(auth)
    except OrgAuthDoesNotExists:
        return False
