from django.core.exceptions import ValidationError

from .exceptions import IntelligenceDoesNotExist, ContentBaseDoesNotExist
from nexus.intelligences.models import (
    Intelligence,
    ContentBase
)


def get_by_intelligence_uuid(intelligence_uuid: str) -> Intelligence:
    try:
        return Intelligence.objects.get(uuid=intelligence_uuid)
    except (Intelligence.DoesNotExist):
        raise IntelligenceDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_by_contentbase_uuid(contentbase_uuid: str) -> ContentBase:
    try:
        return ContentBase.objects.get(uuid=contentbase_uuid)
    except (ContentBase.DoesNotExist):
        raise ContentBaseDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')
