from nexus.intelligences.models import ContentBaseFile

def get_by_uuid(content_base_uuid: str) -> ContentBaseFile:
    try:
        return ContentBaseFile.objects.get(uuid=content_base_uuid)
    except ContentBaseFile.DoesNotExist:
        raise(f"[ ContentBaseFile ] - ContentBaseFile with uuid `{content_base_uuid}` does not exists.")
    except Exception as exception:
        raise(f"[ ContentBaseFile ] - ContentBaseFile error to get - error: `{exception}`")