from django.core.exceptions import ValidationError

from .exceptions import (
    IntelligenceDoesNotExist,
    ContentBaseDoesNotExist,
    ContentBaseTextDoesNotExist
)
from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    ContentBaseLink,
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


def get_by_contentbasetext_uuid(contentbasetext_uuid: str) -> ContentBaseText:
    try:
        return ContentBaseText.objects.get(uuid=contentbasetext_uuid)
    except (ContentBaseText.DoesNotExist):
        raise ContentBaseTextDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')


def get_by_content_base_file_uuid(content_base_uuid: str) -> ContentBaseFile:
    try:
        return ContentBaseFile.objects.get(uuid=content_base_uuid)
    except ContentBaseFile.DoesNotExist:
        raise Exception(f"[ ContentBaseFile ] - ContentBaseFile with uuid `{content_base_uuid}` does not exists.")
    except Exception as exception:
        raise (f"[ ContentBaseFile ] - ContentBaseFile error to get - error: `{exception}`")


def get_by_content_base_link_uuid(content_base_uuid: str) -> ContentBaseFile:
    try:
        return ContentBaseLink.objects.get(uuid=content_base_uuid)
    except ContentBaseLink.DoesNotExist:
        raise Exception(f"[ ContentBaseLink ] - ContentBaseLink with uuid `{content_base_uuid}` does not exists.")
    except Exception as exception:
        raise (f"[ ContentBaseLink ] - ContentBaseFile error to get - error: `{exception}`")


def get_contentbasetext_by_contentbase_uuid(
        content_base_uuid: str
) -> ContentBaseText:
    try:
        return ContentBaseText.objects.get(content_base__uuid=content_base_uuid)
    except (ContentBaseText.DoesNotExist):
        raise ContentBaseTextDoesNotExist()
    except ValidationError:
        raise ValidationError(message='Invalid UUID')
