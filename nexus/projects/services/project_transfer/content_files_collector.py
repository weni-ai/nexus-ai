from __future__ import annotations

from django.conf import settings

from nexus.intelligences.models import (
    ContentBase,
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseText,
    IntegratedIntelligence,
)
from nexus.projects.models import Project
from nexus.projects.services.project_transfer.s3_object_resolver import (
    S3ObjectRef,
    bedrock_metadata_key,
    bedrock_object_key,
    resolve_bedrock_key,
)


class UnsupportedIndexerError(ValueError):
    pass


def _content_base_ids(project: Project) -> list:
    intelligence_ids = IntegratedIntelligence.objects.filter(project=project).values_list("intelligence_id", flat=True)
    return list(ContentBase.objects.filter(intelligence_id__in=intelligence_ids).values_list("pk", flat=True))


def ensure_bedrock_project(project: Project) -> None:
    if project.indexer_database != Project.BEDROCK:
        raise UnsupportedIndexerError(
            f"Project '{project.uuid}' uses indexer '{project.indexer_database}'. "
            "Only Bedrock projects are supported for content file transfer."
        )


def collect_bedrock_s3_objects(
    project: Project,
    *,
    include_metadata: bool = True,
) -> list[S3ObjectRef]:
    ensure_bedrock_project(project)

    bucket = settings.AWS_BEDROCK_BUCKET_NAME
    content_base_ids = _content_base_ids(project)
    objects: list[S3ObjectRef] = []
    seen_keys: set[str] = set()

    def add_object(
        key: str | None,
        *,
        source_model: str,
        source_uuid: str,
        is_metadata: bool = False,
    ) -> None:
        if not key or key in seen_keys:
            return
        seen_keys.add(key)
        objects.append(
            S3ObjectRef(
                bucket=bucket,
                key=key,
                source_model=source_model,
                source_uuid=source_uuid,
                is_metadata=is_metadata,
            )
        )

    for content_base_file in ContentBaseFile.objects.filter(content_base_id__in=content_base_ids, is_active=True):
        content_base_uuid = str(content_base_file.content_base.uuid)
        key = resolve_bedrock_key(
            file_url=content_base_file.file,
            content_base_uuid=content_base_uuid,
            file_name=content_base_file.file_name,
        )
        add_object(
            key,
            source_model="intelligences.ContentBaseFile",
            source_uuid=str(content_base_file.uuid),
        )
        if include_metadata and content_base_file.file_name:
            add_object(
                bedrock_metadata_key(content_base_uuid, content_base_file.file_name),
                source_model="intelligences.ContentBaseFile",
                source_uuid=str(content_base_file.uuid),
                is_metadata=True,
            )

    for content_base_text in ContentBaseText.objects.filter(content_base_id__in=content_base_ids, is_active=True):
        content_base_uuid = str(content_base_text.content_base.uuid)
        key = resolve_bedrock_key(
            file_url=content_base_text.file,
            content_base_uuid=content_base_uuid,
            file_name=content_base_text.file_name,
        )
        add_object(
            key,
            source_model="intelligences.ContentBaseText",
            source_uuid=str(content_base_text.uuid),
        )
        if include_metadata and content_base_text.file_name:
            add_object(
                bedrock_metadata_key(content_base_uuid, content_base_text.file_name),
                source_model="intelligences.ContentBaseText",
                source_uuid=str(content_base_text.uuid),
                is_metadata=True,
            )

    for content_base_link in ContentBaseLink.objects.filter(content_base_id__in=content_base_ids, is_active=True):
        content_base_uuid = str(content_base_link.content_base.uuid)
        if not content_base_link.name:
            continue

        key = bedrock_object_key(content_base_uuid, content_base_link.name)
        add_object(
            key,
            source_model="intelligences.ContentBaseLink",
            source_uuid=str(content_base_link.uuid),
        )
        if include_metadata:
            add_object(
                bedrock_metadata_key(content_base_uuid, content_base_link.name),
                source_model="intelligences.ContentBaseLink",
                source_uuid=str(content_base_link.uuid),
                is_metadata=True,
            )

    return objects
