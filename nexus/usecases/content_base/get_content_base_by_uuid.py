from nexus.intelligences.models import ContentBase

def get_content_base_by_uuid(content_base_uuid: str):
    try:
        content_base = ContentBase.objects.get(uuid=content_base_uuid)
    except ContentBase.DoesNotExist:
        print(f"[get content base] - Content Base with uuid `{content_base_uuid}` does not exists.")
        raise ContentBase.DoesNotExist()
    except Exception as error:
        error_text = f"[get content base] - error: `{error}`"
        print(error_text)
        raise Exception(error_text)
    return content_base