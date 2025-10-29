from django.core.exceptions import ValidationError

from nexus.intelligences.models import ContentBase
from nexus.orgs.models import Org
from nexus.usecases.intelligences.exceptions import ContentBaseDoesNotExist

from .exceptions import OrgDoesNotExists


def get_by_uuid(org_uuid: str) -> Org:
    try:
        return Org.objects.get(uuid=org_uuid)
    except Org.DoesNotExist as e:
        raise OrgDoesNotExists(f"Org `{org_uuid}` does not exists!") from e
    except ValidationError as e:
        raise ValidationError(message="Invalid UUID") from e


def get_org_by_content_base_uuid(content_base_uuid: str) -> Org:
    try:
        content_base = ContentBase.objects.get(uuid=content_base_uuid)
        return content_base.intelligence.org
    except ContentBase.DoesNotExist as e:
        raise ContentBaseDoesNotExist(f"ContentBaseDoesNotExist `{content_base_uuid}` does not exists!") from e
