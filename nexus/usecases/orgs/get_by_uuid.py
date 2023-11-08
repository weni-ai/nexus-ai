from nexus.orgs.models import Org
from .exceptions import OrgDoesNotExists
from django.core.exceptions import ValidationError


def get_by_uuid(org_uuid: str) -> Org:
    try:
        return Org.objects.get(uuid=org_uuid)
    except (Org.DoesNotExist, ValidationError):
        raise OrgDoesNotExists()
