from nexus.orgs.models import Org
from .exceptions import OrgDoesNotExists
from django.core.exceptions import ValidationError


def get_by_uuid(org_uuid: str) -> Org:
    try:
        print("org_uuid: ", org_uuid)
        return Org.objects.get(uuid=org_uuid)
    except (Org.DoesNotExist):
        raise OrgDoesNotExists()
    except ValidationError:
        raise ValidationError()
