from __future__ import annotations

import os
from uuid import UUID

import boto3
from django.conf import settings

from nexus.agents.models import AgentMessage
from nexus.inline_agents.models import InlineAgentMessage
from nexus.projects.models import Project
from nexus.projects.services.project_transfer.s3_object_resolver import S3ObjectRef
from nexus.projects.services.project_transfer.traces_files_constants import (
    INLINE_TRACES_PREFIX,
    LEGACY_TRACES_PREFIX,
    TRACE_TYPE_INLINE,
    TRACE_TYPE_LEGACY,
)


class MissingTracesBucketError(ValueError):
    pass


def inline_traces_bucket() -> str:
    bucket = os.getenv("AWS_BEDROCK_INLINE_TRACES_BUCKET")
    if not bucket:
        raise MissingTracesBucketError(
            "AWS_BEDROCK_INLINE_TRACES_BUCKET is not configured in the environment."
        )
    return bucket


def inline_traces_region() -> str:
    return os.getenv("AWS_BEDROCK_INLINE_TRACES_REGION") or settings.AWS_BEDROCK_REGION_NAME


def legacy_traces_bucket() -> str:
    return settings.AWS_BEDROCK_BUCKET_NAME


def legacy_traces_region() -> str:
    return settings.AWS_BEDROCK_REGION_NAME


def inline_trace_key(project_uuid: str, message_uuid: str) -> str:
    """Same key format used by get_inline_traces and save_inline_trace_events."""
    return f"{INLINE_TRACES_PREFIX}/{project_uuid}/{message_uuid}.jsonl"


def legacy_trace_key(project_uuid: str, message_uuid: str) -> str:
    return f"{LEGACY_TRACES_PREFIX}/{project_uuid}/{message_uuid}.jsonl"


def _parse_inline_message_uuid_from_key(key: str, project_uuid: str) -> str | None:
    prefix = f"{INLINE_TRACES_PREFIX}/{project_uuid}/"
    if not key.startswith(prefix) or not key.endswith(".jsonl"):
        return None

    filename = key[len(prefix) :]
    message_uuid = filename[: -len(".jsonl")]
    try:
        UUID(message_uuid)
    except ValueError:
        return None
    return message_uuid


def collect_inline_trace_s3_objects(project: Project) -> list[S3ObjectRef]:
    project_uuid = str(project.uuid)
    bucket = inline_traces_bucket()
    region = inline_traces_region()
    prefix = f"{INLINE_TRACES_PREFIX}/{project_uuid}/"
    client = boto3.client("s3", region_name=region)

    message_uuids_by_key: dict[str, str] = {}
    for message in InlineAgentMessage.objects.filter(project=project).only("uuid"):
        key = inline_trace_key(project_uuid, str(message.uuid))
        message_uuids_by_key[key] = str(message.uuid)

    objects: list[S3ObjectRef] = []
    seen_keys: set[str] = set()
    paginator = client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key in seen_keys or not key.endswith(".jsonl"):
                continue

            seen_keys.add(key)
            message_uuid = message_uuids_by_key.get(key) or _parse_inline_message_uuid_from_key(key, project_uuid)
            if not message_uuid:
                continue

            objects.append(
                S3ObjectRef(
                    bucket=bucket,
                    key=key,
                    source_model="inline_agents.InlineAgentMessage",
                    source_uuid=message_uuid,
                    is_metadata=False,
                    trace_type=TRACE_TYPE_INLINE,
                )
            )

    if objects:
        return objects

    for key, message_uuid in message_uuids_by_key.items():
        objects.append(
            S3ObjectRef(
                bucket=bucket,
                key=key,
                source_model="inline_agents.InlineAgentMessage",
                source_uuid=message_uuid,
                is_metadata=False,
                trace_type=TRACE_TYPE_INLINE,
            )
        )

    return objects


def collect_trace_s3_objects(
    project: Project,
    *,
    include_inline: bool = True,
    include_legacy: bool = True,
) -> list[S3ObjectRef]:
    project_uuid = str(project.uuid)
    objects: list[S3ObjectRef] = []
    seen_keys: set[tuple[str, str]] = set()

    def add_object(
        *,
        bucket: str,
        key: str,
        source_model: str,
        source_uuid: str,
        trace_type: str,
    ) -> None:
        dedupe_key = (bucket, key)
        if dedupe_key in seen_keys:
            return
        seen_keys.add(dedupe_key)
        objects.append(
            S3ObjectRef(
                bucket=bucket,
                key=key,
                source_model=source_model,
                source_uuid=source_uuid,
                is_metadata=False,
                trace_type=trace_type,
            )
        )

    if include_inline:
        objects.extend(collect_inline_trace_s3_objects(project))

    if include_legacy:
        bucket = legacy_traces_bucket()
        for message in AgentMessage.objects.filter(project=project).only("uuid"):
            add_object(
                bucket=bucket,
                key=legacy_trace_key(project_uuid, str(message.uuid)),
                source_model="agents.AgentMessage",
                source_uuid=str(message.uuid),
                trace_type=TRACE_TYPE_LEGACY,
            )

    return objects
