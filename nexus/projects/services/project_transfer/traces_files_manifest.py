from __future__ import annotations

import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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
    DEFAULT_IMPORT_WORKERS,
    DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS,
    INLINE_TRACES_PREFIX,
    LEGACY_TRACES_PREFIX,
    TRACES_FILES_SCHEMA_VERSION,
    TRACE_TYPE_INLINE,
    TRACE_TYPE_LEGACY,
)
from nexus.projects.services.project_transfer.s3_object_resolver import S3ObjectRef

ProgressCallback = Callable[[int, int, str, str], None]

_thread_local = threading.local()


@dataclass(frozen=True)
class _TraceImportJob:
    dest_key: str
    bucket: str
    region: str
    presigned_url: str


@dataclass(frozen=True)
class _TraceImportResult:
    dest_key: str
    status: str
    error: str | None = None


def _thread_s3_client(region: str):
    clients = getattr(_thread_local, "s3_clients", None)
    if clients is None:
        clients = {}
        _thread_local.s3_clients = clients
    if region not in clients:
        clients[region] = boto3.client("s3", region_name=region)
    return clients[region]


class TraceFilesManifestExporter:
    def __init__(
        self,
        project: Project,
        *,
        expires_in: int = DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS,
        include_inline: bool = True,
        include_legacy: bool = False,
    ):
        self.project = project
        self.expires_in = expires_in
        self.include_inline = include_inline
        self.include_legacy = include_legacy
        self._s3_clients: dict[str, Any] = {}

    def build_manifest(self) -> dict[str, Any]:
        collected = collect_trace_s3_objects(
            self.project,
            include_inline=self.include_inline,
            include_legacy=self.include_legacy,
        )
        exported_at = datetime.now(timezone.utc)
        expires_at = exported_at + timedelta(seconds=self.expires_in)

        manifest_objects = []
        for obj, trace_type in collected:
            region = inline_traces_region() if trace_type == TRACE_TYPE_INLINE else legacy_traces_region()
            manifest_objects.append(
                {
                    "key": obj.key,
                    "bucket": obj.bucket,
                    "region": region,
                    "presigned_url": self._presign_get_url(obj, region),
                    "source_model": obj.source_model,
                    "source_uuid": obj.source_uuid,
                    "trace_type": trace_type,
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
        workers: int = DEFAULT_IMPORT_WORKERS,
        progress_callback: ProgressCallback | None = None,
    ):
        self.manifest = manifest
        self.dest_inline_bucket = dest_inline_bucket
        self.dest_legacy_bucket = dest_legacy_bucket or legacy_traces_bucket()
        self.dest_inline_region = dest_inline_region or inline_traces_region()
        self.dest_legacy_region = dest_legacy_region or legacy_traces_region()
        self.dest_project_uuid = str(dest_project_uuid) if dest_project_uuid else None
        self.skip_existing = skip_existing
        self.dry_run = dry_run
        self.workers = max(1, workers)
        self.progress_callback = progress_callback
        self._stats_lock = threading.Lock()
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
        workers: int = DEFAULT_IMPORT_WORKERS,
        progress_callback: ProgressCallback | None = None,
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
            workers=workers,
            progress_callback=progress_callback,
        )

    def import_files(self) -> dict[str, Any]:
        source_project_uuid = self.manifest.get("source_project_uuid")
        jobs = self._build_jobs(source_project_uuid)
        self.stats["total"] = len(jobs)

        if not jobs:
            return {"stats": self.stats, "errors": self.errors}

        if self.dry_run:
            for index, job in enumerate(jobs, start=1):
                self._increment_stat("copied")
                self._emit_progress(index, len(jobs), job.dest_key, "copied")
            return {"stats": self.stats, "errors": self.errors}

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._process_job, job): job for job in jobs}
            completed = 0
            for future in as_completed(futures):
                job = futures[future]
                result = future.result()
                completed += 1
                self._apply_result(result)
                self._emit_progress(completed, len(jobs), result.dest_key, result.status)

        return {"stats": self.stats, "errors": self.errors}

    def _build_jobs(self, source_project_uuid: str | None) -> list[_TraceImportJob]:
        jobs: list[_TraceImportJob] = []

        for entry in self.manifest.get("objects", []):
            presigned_url = entry.get("presigned_url")
            if not presigned_url:
                dest_key = self._resolve_dest_key(entry.get("key", "<missing-key>"), source_project_uuid)
                self._register_failure(dest_key, "Missing presigned_url")
                continue

            trace_type = entry.get("trace_type")
            bucket, region = self._destination_bucket_and_region(trace_type, entry)
            dest_key = self._resolve_dest_key(entry["key"], source_project_uuid)
            jobs.append(
                _TraceImportJob(
                    dest_key=dest_key,
                    bucket=bucket,
                    region=region,
                    presigned_url=presigned_url,
                )
            )

        return jobs

    def _process_job(self, job: _TraceImportJob) -> _TraceImportResult:
        if self.skip_existing and self._object_exists(job.bucket, job.region, job.dest_key):
            return _TraceImportResult(dest_key=job.dest_key, status="skipped")

        try:
            self._download_and_upload(job.bucket, job.region, job.dest_key, job.presigned_url)
        except Exception as exc:
            return _TraceImportResult(dest_key=job.dest_key, status="failed", error=str(exc))

        return _TraceImportResult(dest_key=job.dest_key, status="copied")

    def _apply_result(self, result: _TraceImportResult) -> None:
        if result.status == "failed":
            self._register_failure(result.dest_key, result.error or "Unknown error")
            return
        self._increment_stat(result.status)

    def _increment_stat(self, status: str) -> None:
        with self._stats_lock:
            if status in self.stats:
                self.stats[status] += 1

    def _emit_progress(self, completed: int, total: int, key: str, status: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(completed, total, key, status)

    def _manifest_has_trace_type(self, trace_type: str) -> bool:
        return any(entry.get("trace_type") == trace_type for entry in self.manifest.get("objects", []))

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

    def _object_exists(self, bucket: str, region: str, key: str) -> bool:
        try:
            _thread_s3_client(region).head_object(Bucket=bucket, Key=key)
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
        _thread_s3_client(region).upload_fileobj(buffer, bucket, key)

    def _register_failure(self, key: str, message: str) -> None:
        with self._stats_lock:
            self.stats["failed"] += 1
            self.errors.append(f"{key}: {message}")
