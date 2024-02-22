from nexus.orgs.models import Org
from nexus.intelligences.models import ContentBase
from .exceptions import OrgDoesNotExists
from django.core.exceptions import ValidationError
from nexus.usecases.intelligences.exceptions import ContentBaseDoesNotExist


def get_by_uuid(org_uuid: str) -> Org:
    try:
        return Org.objects.get(uuid=org_uuid)
    except (Org.DoesNotExist):
        raise OrgDoesNotExists(f"Org `{org_uuid}` does not exists!")
    except ValidationError:
        raise ValidationError(message="Invalid UUID")


def get_org_by_content_base_uuid(content_base_uuid: str) -> Org:
    try:
        content_base = ContentBase.objects.get(uuid=content_base_uuid)
        return content_base.intelligence.org
    except ContentBase.DoesNotExist:
        raise ContentBaseDoesNotExist(f"ContentBaseDoesNotExist `{content_base_uuid}` does not exists!")
    except Org.DoesNotExist:
        raise OrgDoesNotExists()
