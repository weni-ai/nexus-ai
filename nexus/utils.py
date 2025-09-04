from django.conf import settings

def get_datasource_id(project_uuid: str | None) -> str:
    if project_uuid in settings.PROJECTS_WITH_LARGE_DATASOURCE:
        return settings.AWS_BEDROCK_LARGE_DATASOURCE_ID
    return settings.AWS_BEDROCK_DATASOURCE_ID
