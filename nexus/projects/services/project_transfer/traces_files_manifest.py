from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import boto3
import requests
from botocore.exceptions import ClientError
from django.conf import settings

from nexus.projects.models import Project
from nexus.projects.services.project_transfer.traces_files_collector import (
    MissingTracesBucketError,
    collect_trace_s3_objects,
    inline_traces_bucket,
    inline_traces_region,
    legacy_traces_bucket,
    legacy_traces_region,
)
from nexus.projects.services.project_transfer.traces_files_constants import (
    DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS,
    INLINE_TRACES_PREFIX,
    LEGACY_TRACES_PREFIX,
    TRACES_FILES_SCHEMA_VERSION,
    TRACE_TYPE_INLINE,
    TRACE_TYPE_LEGACY,
)
from nexus.projects.services.project_transfer.s3_object_resolver import S3ObjectRef


class TraceFilesManifestExporter:
    def __init__(
        self,
        project: Project,
        *,
        expires_in: int = DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS,
        include_inline: bool = True,
        include_legacy: bool = True,
    ):
        self.project = project
        self.expires_in = expires_in
        self.include_inline = include_inline
        self.include_legacy = include_legacy
        self._s3_clients: dict[str, Any] = {}

    def build_manifest(self) -> dict[str, Any]:
        objects = collect_trace_s3_objects(
            self.project,
            include_inline=self.include_inline,
            include_legacy=self.include_legacy,
        )
        exported_at = datetime.now(timezone.utc)
        expires_at = exported_at + timedelta(seconds=self.expires_in)

        manifest_objects = []
        for obj in objects:
            region = self._region_for_object(obj)
            manifest_objects.append(
                {
                    "key": obj.key,
                    "bucket": obj.bucket,
                    "region": region,
                    "presigned_url": self._presign_get_url(obj, region),
                    "source_model": obj.source_model,
                    "source_uuid": obj.source_uuid,
                    "trace_type": obj.trace_type,
                }
            )

        source_buckets: dict[str, dict[str, str]] = {}
        if self.include_inline:
            source_buckets[TRACE_TYPE_INLINE] = {
                "bucket": inline_traces_bucket(),
                "region": inline_traces_region(),
            }
        if self.include_legacy:
            source_buckets[TRACE_TYPE_LEGACY] = {
                "bucket": legacy_traces_bucket(),
                "region": legacy_traces_region(),
            }

        return {
            "schema_version": TRACES_FILES_SCHEMA_VERSION,
            "exported_at": exported_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "presigned_url_expires_in": self.expires_in,
            "source_project_uuid": str(self.project.uuid),
            "source_buckets": source_buckets,
            "object_count": len(manifest_objects),
            "objects": manifest_objects,
        }

    def export_json(self) -> str:
        return json.dumps(self.build_manifest(), indent=2, ensure_ascii=False)

    def _region_for_object(self, obj: S3ObjectRef) -> str:
        if obj.trace_type == TRACE_TYPE_INLINE:
            return inline_traces_region()
        return legacy_traces_region()

    def _s3_client(self, region: str):
        if region not in self._s3_clients:
            self._s3_clients[region] = boto3.client("s3", region_name=region)
        return self._s3_clients[region]

    def _presign_get_url(self, obj: S3ObjectRef, region: str) -> str:
        return self._s3_client(region).generate_presigned_url(
            "get_object",
            Params={"Bucket": obj.bucket, "Key": obj.key},
            ExpiresIn=self.expires_in,
        )


class TraceFilesManifestImporter:
    def __init__(
        self,
        manifest: dict[str, Any],
        *,
        dest_inline_bucket: str | None = None,
        dest_legacy_bucket: str | None = None,
        dest_inline_region: str | None = None,
        dest_legacy_region: str | None = None,
        dest_project_uuid: str | None = None,
        skip_existing: bool = False,
        dry_run: bool = False,
    ):
        self.manifest = manifest
        self.dest_inline_bucket = dest_inline_bucket
        self.dest_legacy_bucket = dest_legacy_bucket or legacy_traces_bucket()
        self.dest_inline_region = dest_inline_region or inline_traces_region()
        self.dest_legacy_region = dest_legacy_region or legacy_traces_region()
        self.dest_project_uuid = str(dest_project_uuid) if dest_project_uuid else None
        self.skip_existing = skip_existing
        self.dry_run = dry_run
        self._s3_clients: dict[tuple[str, str], Any] = {}
        self.stats = {"copied": 0, "skipped": 0, "failed": 0, "total": 0}
        self.errors: list[str] = []

        if self.dest_inline_bucket is None and self._manifest_has_trace_type(TRACE_TYPE_INLINE):
            self.dest_inline_bucket = inline_traces_bucket()

    @classmethod
    def from_json(
        cls,
        raw: str,
        *,
        dest_inline_bucket: str | None = None,
        dest_legacy_bucket: str | None = None,
        dest_inline_region: str | None = None,
        dest_legacy_region: str | None = None,
        dest_project_uuid: str | None = None,
        skip_existing: bool = False,
        dry_run: bool = False,
    ) -> "TraceFilesManifestImporter":
        manifest = json.loads(raw)
        if manifest.get("schema_version") != TRACES_FILES_SCHEMA_VERSION:
            raise ValueError(f"Unsupported manifest schema version: {manifest.get('schema_version')}")
        return cls(
            manifest,
            dest_inline_bucket=dest_inline_bucket,
            dest_legacy_bucket=dest_legacy_bucket,
            dest_inline_region=dest_inline_region,
            dest_legacy_region=dest_legacy_region,
            dest_project_uuid=dest_project_uuid,
            skip_existing=skip_existing,
            dry_run=dry_run,
        )

    def import_files(self) -> dict[str, Any]:
        source_project_uuid = self.manifest.get("source_project_uuid")

        for entry in self.manifest.get("objects", []):
            self.stats["total"] += 1
            source_key = entry["key"]
            dest_key = self._resolve_dest_key(source_key, source_project_uuid)
            trace_type = entry.get("trace_type")
            bucket, region = self._destination_bucket_and_region(trace_type, entry)
            presigned_url = entry.get("presigned_url")

            if not presigned_url:
                self._register_failure(dest_key, "Missing presigned_url")
                continue

            if self.skip_existing and self._object_exists(bucket, region, dest_key):
                self.stats["skipped"] += 1
                continue

            if self.dry_run:
                self.stats["copied"] += 1
                continue

            try:
                self._download_and_upload(bucket, region, dest_key, presigned_url)
                self.stats["copied"] += 1
            except Exception as exc:
                self._register_failure(dest_key, str(exc))

        return {"stats": self.stats, "errors": self.errors}

    def _manifest_has_trace_type(self, trace_type: str) -> bool:
        return any(
            entry.get("trace_type") == trace_type for entry in self.manifest.get("objects", [])
        )

    def _resolve_dest_key(self, source_key: str, source_project_uuid: str | None) -> str:
        if not self.dest_project_uuid or not source_project_uuid:
            return source_key
        if self.dest_project_uuid == source_project_uuid:
            return source_key

        for prefix in (INLINE_TRACES_PREFIX, LEGACY_TRACES_PREFIX):
            source_prefix = f"{prefix}/{source_project_uuid}/"
            dest_prefix = f"{prefix}/{self.dest_project_uuid}/"
            if source_key.startswith(source_prefix):
                return dest_prefix + source_key[len(source_prefix) :]

        return source_key

    def _destination_bucket_and_region(
        self,
        trace_type: str | None,
        entry: dict[str, Any],
    ) -> tuple[str, str]:
        if trace_type == TRACE_TYPE_INLINE:
            return self.dest_inline_bucket, self.dest_inline_region
        if trace_type == TRACE_TYPE_LEGACY:
            return self.dest_legacy_bucket, self.dest_legacy_region

        source_buckets = self.manifest.get("source_buckets", {})
        inline_bucket = source_buckets.get(TRACE_TYPE_INLINE, {}).get("bucket")
        if inline_bucket and entry.get("bucket") == inline_bucket:
            return self.dest_inline_bucket, self.dest_inline_region
        return self.dest_legacy_bucket, self.dest_legacy_region

    def _s3_client(self, region: str):
        key = (region,)
        if key not in self._s3_clients:
            self._s3_clients[key] = boto3.client("s3", region_name=region)
        return self._s3_clients[key]

    def _object_exists(self, bucket: str, region: str, key: str) -> bool:
        try:
            self._s3_client(region).head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound", "403"}:
                return False
            raise

    def _download_and_upload(self, bucket: str, region: str, key: str, presigned_url: str) -> None:
        response = requests.get(presigned_url, timeout=300)
        response.raise_for_status()

        buffer = BytesIO(response.content)
        self._s3_client(region).upload_fileobj(buffer, bucket, key)

    def _register_failure(self, key: str, message: str) -> None:
        self.stats["failed"] += 1
        self.errors.append(f"{key}: {message}")
