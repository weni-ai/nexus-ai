from nexus.intelligences.models import ContentBase

def get_by_uuid(content_base_uuid: str) -> ContentBase:
    try:
        return ContentBase.objects.get(uuid=content_base_uuid)
    except ContentBase.DoesNotExist:
        raise(f"[ ContentBase ] - ContentBase with uuid `{content_base_uuid}` does not exists.")
    except Exception as exception:
        raise(f"[ ContentBase ] - ContentBase error to get - error: `{exception}`")
