from django.core.exceptions import ValidationError

from .exceptions import IntelligenceDoesNotExist
from nexus.intelligences.models import Intelligence


def get_by_uuid(intelligence_uuid: str) -> Intelligence:
    try:
        return Intelligence.objects.get(uuid=intelligence_uuid)
    except (Intelligence.DoesNotExist):
        raise IntelligenceDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')
