from django.conf import settings


def get_datasource_id(project_uuid: str | None) -> str:
    if project_uuid:
        try:
            from nexus.projects.models import Project

            project = Project.objects.get(uuid=project_uuid)
            if (
                project.bedrock_ingestion_strategy == Project.BEDROCK_INGESTION_DIRECT
                and settings.AWS_BEDROCK_DIRECT_DATASOURCE_ID
            ):
                return settings.AWS_BEDROCK_DIRECT_DATASOURCE_ID
        except Project.DoesNotExist:
            pass
    if project_uuid in settings.PROJECTS_WITH_LARGE_DATASOURCE:
        return settings.AWS_BEDROCK_LARGE_DATASOURCE_ID
    return settings.AWS_BEDROCK_DATASOURCE_ID
