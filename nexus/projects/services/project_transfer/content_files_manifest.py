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
from nexus.projects.services.project_transfer.content_files_collector import collect_bedrock_s3_objects
from nexus.projects.services.project_transfer.content_files_constants import (
    CONTENT_FILES_SCHEMA_VERSION,
    DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS,
)
from nexus.projects.services.project_transfer.s3_object_resolver import S3ObjectRef


class ContentFilesManifestExporter:
    def __init__(
        self,
        project: Project,
        *,
        expires_in: int = DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS,
        include_metadata: bool = True,
    ):
        self.project = project
        self.expires_in = expires_in
        self.include_metadata = include_metadata
        self.s3_client = boto3.client("s3", region_name=settings.AWS_BEDROCK_REGION_NAME)

    def build_manifest(self) -> dict[str, Any]:
        objects = collect_bedrock_s3_objects(self.project, include_metadata=self.include_metadata)
        exported_at = datetime.now(timezone.utc)
        expires_at = exported_at + timedelta(seconds=self.expires_in)

        manifest_objects = []
        for obj in objects:
            manifest_objects.append(
                {
                    "key": obj.key,
                    "bucket": obj.bucket,
                    "presigned_url": self._presign_get_url(obj),
                    "source_model": obj.source_model,
                    "source_uuid": obj.source_uuid,
                    "is_metadata": obj.is_metadata,
                }
            )

        return {
            "schema_version": CONTENT_FILES_SCHEMA_VERSION,
            "exported_at": exported_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "presigned_url_expires_in": self.expires_in,
            "source_project_uuid": str(self.project.uuid),
            "source_bucket": settings.AWS_BEDROCK_BUCKET_NAME,
            "source_region": settings.AWS_BEDROCK_REGION_NAME,
            "object_count": len(manifest_objects),
            "objects": manifest_objects,
        }

    def export_json(self) -> str:
        return json.dumps(self.build_manifest(), indent=2, ensure_ascii=False)

    def _presign_get_url(self, obj: S3ObjectRef) -> str:
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": obj.bucket, "Key": obj.key},
            ExpiresIn=self.expires_in,
        )


class ContentFilesManifestImporter:
    def __init__(
        self,
        manifest: dict[str, Any],
        *,
        dest_bucket: str,
        dest_region: str | None = None,
        skip_existing: bool = False,
        dry_run: bool = False,
    ):
        self.manifest = manifest
        self.dest_bucket = dest_bucket
        self.dest_region = dest_region or settings.AWS_BEDROCK_REGION_NAME
        self.skip_existing = skip_existing
        self.dry_run = dry_run
        self.s3_client = boto3.client("s3", region_name=self.dest_region)
        self.stats = {"copied": 0, "skipped": 0, "failed": 0, "total": 0}
        self.errors: list[str] = []

    @classmethod
    def from_json(
        cls,
        raw: str,
        *,
        dest_bucket: str,
        dest_region: str | None = None,
        skip_existing: bool = False,
        dry_run: bool = False,
    ) -> "ContentFilesManifestImporter":
        manifest = json.loads(raw)
        if manifest.get("schema_version") != CONTENT_FILES_SCHEMA_VERSION:
            raise ValueError(f"Unsupported manifest schema version: {manifest.get('schema_version')}")
        return cls(
            manifest,
            dest_bucket=dest_bucket,
            dest_region=dest_region,
            skip_existing=skip_existing,
            dry_run=dry_run,
        )

    def import_files(self) -> dict[str, Any]:
        for entry in self.manifest.get("objects", []):
            self.stats["total"] += 1
            key = entry["key"]
            presigned_url = entry.get("presigned_url")

            if not presigned_url:
                self._register_failure(key, "Missing presigned_url")
                continue

            if self.skip_existing and self._object_exists(key):
                self.stats["skipped"] += 1
                continue

            if self.dry_run:
                self.stats["copied"] += 1
                continue

            try:
                self._download_and_upload(key, presigned_url)
                self.stats["copied"] += 1
            except Exception as exc:
                self._register_failure(key, str(exc))

        return {"stats": self.stats, "errors": self.errors}

    def _object_exists(self, key: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.dest_bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound", "403"}:
                return False
            raise

    def _download_and_upload(self, key: str, presigned_url: str) -> None:
        response = requests.get(presigned_url, timeout=300)
        response.raise_for_status()

        buffer = BytesIO(response.content)
        self.s3_client.upload_fileobj(buffer, self.dest_bucket, key)

    def _register_failure(self, key: str, message: str) -> None:
        self.stats["failed"] += 1
        self.errors.append(f"{key}: {message}")
