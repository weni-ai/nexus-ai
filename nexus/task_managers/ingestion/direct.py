import hashlib
import json
import logging
from time import sleep
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

import pendulum
from botocore.exceptions import ClientError
from django.conf import settings

from nexus.intelligences.models import ContentBaseFile
from nexus.projects.models import Project
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.ingestion.constants import (
    FAILURE_STATUSES,
    IN_PROGRESS_STATUSES,
    NON_RETRYABLE_ERROR_CODES,
    PARTIAL_STATUSES,
    PATH_DIRECT,
    PATH_JOB_FALLBACK,
    STRATEGY_DIRECT_WITH_FALLBACK,
    SUCCESS_STATUSES,
    TRANSIENT_ERROR_CODES,
)
from nexus.task_managers.ingestion.telemetry import log_ingestion_completed, log_ingestion_failed
from nexus.task_managers.models import TaskManager
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase

logger = logging.getLogger(__name__)


def build_client_token(project_uuid: str, content_base_file: ContentBaseFile) -> str:
    version_marker = content_base_file.modified_at or content_base_file.created_at
    marker_iso = pendulum.instance(version_marker).in_timezone("UTC").to_iso8601_string()
    raw = f"{project_uuid}:{content_base_file.uuid}:{marker_iso}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_s3_uri(bucket_name: str, object_key: str) -> str:
    """Build an S3 URI with a safely encoded object key (spaces and special chars)."""
    return f"s3://{bucket_name}/{quote(object_key, safe='/')}"


def https_file_url_to_s3_uri(file_url: str, bucket_name: str, region_name: str) -> str:
    """Convert HTTPS S3 object URLs to s3://bucket/key (supports regional and global endpoints)."""
    if file_url.startswith("s3://"):
        return file_url

    parsed = urlparse(file_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported file URL for S3 ingestion: {file_url}")

    host = parsed.netloc
    object_key = unquote(parsed.path.lstrip("/"))
    if not object_key:
        raise ValueError(f"Unsupported file URL for S3 ingestion: {file_url}")

    virtual_hosts = (
        f"{bucket_name}.s3.{region_name}.amazonaws.com",
        f"{bucket_name}.s3.amazonaws.com",
    )
    if host in virtual_hosts:
        return build_s3_uri(bucket_name, object_key)

    path_style_hosts = (f"s3.{region_name}.amazonaws.com", "s3.amazonaws.com")
    if host in path_style_hosts and object_key.startswith(f"{bucket_name}/"):
        return build_s3_uri(bucket_name, object_key[len(bucket_name) + 1 :])

    raise ValueError(f"Unsupported file URL for S3 ingestion: {file_url}")


def _utc_now() -> pendulum.DateTime:
    return pendulum.now("UTC")


def _iso(dt: Optional[pendulum.DateTime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.in_timezone("UTC").to_iso8601_string()


def _should_fallback(strategy: str) -> bool:
    return strategy == STRATEGY_DIRECT_WITH_FALLBACK


def _is_terminal_failure_status(status: str) -> bool:
    return status in FAILURE_STATUSES or status in PARTIAL_STATUSES


def _client_error_details(exc: ClientError) -> Dict[str, Any]:
    response = exc.response or {}
    error = response.get("Error", {})
    metadata = response.get("ResponseMetadata", {})
    return {
        "exception_type": error.get("Code") or type(exc).__name__,
        "error_message": str(exc),
        "bedrock_error_code": error.get("Code"),
        "bedrock_error_message": error.get("Message"),
        "bedrock_error": error,
        "bedrock_response_metadata": {
            "request_id": metadata.get("RequestId"),
            "http_status_code": metadata.get("HTTPStatusCode"),
        },
    }


def _exception_details(exc: Exception) -> Dict[str, Any]:
    return {
        "exception_type": type(exc).__name__,
        "error_message": str(exc),
    }


def _log_direct_ingest_failure(
    *,
    strategy: str,
    submitted_at: pendulum.DateTime,
    api_returned_at: Optional[pendulum.DateTime],
    final_status_at: pendulum.DateTime,
    content_base_uuid: str,
    file_uuid: str,
    project_uuid: str,
    s3_uri: str,
    last_exception: Optional[Exception],
    document_status: str,
    document_status_reason: str,
    last_ingest_result: Optional[Dict[str, Any]],
    last_document_detail: Optional[Dict[str, Any]],
) -> None:
    payload: Dict[str, Any] = {
        "path": PATH_DIRECT,
        "strategy": strategy,
        "status": "fail",
        "submitted_at": _iso(submitted_at),
        "api_returned_at": _iso(api_returned_at),
        "final_status_at": _iso(final_status_at),
        "content_base_uuid": content_base_uuid,
        "file_uuid": file_uuid,
        "project_uuid": project_uuid,
        "document_type": "file",
        "s3_uri": s3_uri,
        "bedrock_document_status": document_status or None,
        "bedrock_status_reason": document_status_reason or None,
    }
    if last_ingest_result:
        payload["bedrock_ingest_response"] = last_ingest_result.get("raw_response")
    if last_document_detail:
        payload["bedrock_document_detail"] = last_document_detail
    if isinstance(last_exception, ClientError):
        payload.update(_client_error_details(last_exception))
    elif last_exception:
        payload.update(_exception_details(last_exception))

    log_ingestion_failed(payload)
    logger.error(
        "[Bedrock] Direct ingest failed: %s",
        json.dumps(payload, default=str),
    )


def _wait_for_terminal_document_status(
    file_database: BedrockFileDatabase,
    s3_uri: str,
    initial_status: str,
) -> Tuple[str, str, Dict[str, Any]]:
    """Poll GetKnowledgeBaseDocuments until the document leaves in-progress states."""
    status = initial_status
    status_reason = ""
    last_detail: Dict[str, Any] = {}
    if status not in IN_PROGRESS_STATUSES:
        return status, status_reason, last_detail

    poll_interval = settings.BEDROCK_DIRECT_INGEST_POLL_INTERVAL_SECONDS
    max_attempts = settings.BEDROCK_DIRECT_INGEST_POLL_MAX_ATTEMPTS
    for attempt in range(max_attempts):
        logger.info(
            "[Bedrock] Direct ingest document status %s (poll %s/%s)",
            status,
            attempt + 1,
            max_attempts,
        )
        sleep(poll_interval)
        last_detail = file_database.get_knowledge_base_document_detail(s3_uri)
        status = last_detail["status"]
        status_reason = last_detail.get("statusReason") or ""
        if status not in IN_PROGRESS_STATUSES:
            if status_reason:
                logger.info("[Bedrock] Direct ingest terminal status reason: %s", status_reason)
            return status, status_reason, last_detail
    return status, status_reason, last_detail


def _validate_search(file_database: BedrockFileDatabase, content_base_uuid: str, max_attempts: int = 3) -> bool:
    for attempt in range(max_attempts):
        try:
            file_database.search_data(content_base_uuid=content_base_uuid, text="test", number_of_results=1)
            return True
        except Exception as exc:
            logger.warning(
                "Direct ingest search validation attempt %s failed: %s",
                attempt + 1,
                exc,
            )
            if attempt < max_attempts - 1:
                sleep(2)
    return False


def run_direct_ingest(
    *,
    project: Project,
    project_uuid: str,
    content_base_uuid: str,
    content_base_file: ContentBaseFile,
    s3_uri: str,
    strategy: str,
    task_manager_uuid: str,
) -> Tuple[bool, str]:
    """
    Run direct Bedrock document ingestion with retries.

    Returns (success, effective_path).
    """
    submitted_at = _utc_now()
    client_token = build_client_token(project_uuid, content_base_file)
    file_database = BedrockFileDatabase(project_uuid=project_uuid)
    max_retries = settings.BEDROCK_DIRECT_INGEST_MAX_RETRIES
    backoff_base = settings.BEDROCK_DIRECT_INGEST_BACKOFF_BASE_SECONDS

    last_exception: Optional[Exception] = None
    document_status = ""
    document_status_reason = ""
    last_ingest_result: Optional[Dict[str, Any]] = None
    last_document_detail: Optional[Dict[str, Any]] = None
    api_returned_at: Optional[pendulum.DateTime] = None

    for attempt in range(max_retries + 1):
        try:
            last_ingest_result = file_database.ingest_knowledge_base_documents(
                s3_uri=s3_uri,
                client_token=client_token,
                content_base_uuid=str(content_base_uuid),
                file_uuid=str(content_base_file.uuid),
            )
            api_returned_at = _utc_now()
            document_status, document_status_reason, last_document_detail = _wait_for_terminal_document_status(
                file_database,
                s3_uri,
                last_ingest_result.get("document_status", ""),
            )
            if document_status in SUCCESS_STATUSES:
                break
            if _is_terminal_failure_status(document_status):
                last_exception = RuntimeError(
                    f"Bedrock document status: {document_status}"
                    + (f" ({document_status_reason})" if document_status_reason else "")
                )
                break
            if document_status in IN_PROGRESS_STATUSES:
                last_exception = RuntimeError(f"Bedrock document status timed out while {document_status}")
                break
            last_exception = RuntimeError(f"Unexpected Bedrock document status: {document_status}")
            break
        except ClientError as exc:
            api_returned_at = _utc_now()
            last_exception = exc
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in NON_RETRYABLE_ERROR_CODES:
                break
            if error_code in TRANSIENT_ERROR_CODES and attempt < max_retries:
                sleep(backoff_base * (2**attempt))
                continue
            break
        except Exception as exc:
            api_returned_at = _utc_now()
            last_exception = exc
            break

    task_manager_usecase = CeleryTaskManagerUseCase()
    final_status_at = _utc_now()

    if document_status in SUCCESS_STATUSES:
        first_search_hit_at = None
        if _validate_search(file_database, content_base_uuid):
            first_search_hit_at = _utc_now()
        task_manager_usecase.update_task_status(
            task_manager_uuid,
            TaskManager.STATUS_SUCCESS,
            "file",
        )
        log_ingestion_completed(
            {
                "path": PATH_DIRECT,
                "strategy": strategy,
                "status": "success",
                "submitted_at": _iso(submitted_at),
                "api_returned_at": _iso(api_returned_at),
                "final_status_at": _iso(final_status_at),
                "first_search_hit_at": _iso(first_search_hit_at),
                "content_base_uuid": str(content_base_uuid),
                "file_uuid": str(content_base_file.uuid),
                "project_uuid": project_uuid,
                "document_type": "file",
                "bedrock_document_status": document_status,
            }
        )
        return True, PATH_DIRECT

    if _should_fallback(strategy):
        if last_exception or document_status:
            _log_direct_ingest_failure(
                strategy=strategy,
                submitted_at=submitted_at,
                api_returned_at=api_returned_at,
                final_status_at=final_status_at,
                content_base_uuid=str(content_base_uuid),
                file_uuid=str(content_base_file.uuid),
                project_uuid=project_uuid,
                s3_uri=s3_uri,
                last_exception=last_exception,
                document_status=document_status,
                document_status_reason=document_status_reason,
                last_ingest_result=last_ingest_result,
                last_document_detail=last_document_detail,
            )
        return False, PATH_JOB_FALLBACK

    task_manager_usecase.update_task_status(task_manager_uuid, TaskManager.STATUS_FAIL, "file")
    if last_exception or document_status:
        _log_direct_ingest_failure(
            strategy=strategy,
            submitted_at=submitted_at,
            api_returned_at=api_returned_at,
            final_status_at=final_status_at,
            content_base_uuid=str(content_base_uuid),
            file_uuid=str(content_base_file.uuid),
            project_uuid=project_uuid,
            s3_uri=s3_uri,
            last_exception=last_exception,
            document_status=document_status,
            document_status_reason=document_status_reason,
            last_ingest_result=last_ingest_result,
            last_document_detail=last_document_detail,
        )
    return False, PATH_DIRECT
