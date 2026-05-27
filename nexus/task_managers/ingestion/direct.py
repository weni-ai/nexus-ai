import hashlib
import logging
from time import sleep
from typing import Optional, Tuple

import pendulum
from botocore.exceptions import ClientError
from django.conf import settings

from nexus.intelligences.models import ContentBaseFile
from nexus.projects.models import Project
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.ingestion.constants import (
    FAILURE_STATUSES,
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


def https_file_url_to_s3_uri(file_url: str, bucket_name: str, region_name: str) -> str:
    prefix = f"https://{bucket_name}.s3.{region_name}.amazonaws.com/"
    if file_url.startswith(prefix):
        key = file_url[len(prefix) :]
        return f"s3://{bucket_name}/{key}"
    if file_url.startswith("s3://"):
        return file_url
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
    api_returned_at: Optional[pendulum.DateTime] = None

    for attempt in range(max_retries + 1):
        try:
            result = file_database.ingest_knowledge_base_documents(
                s3_uri=s3_uri,
                client_token=client_token,
                content_base_uuid=str(content_base_uuid),
                file_uuid=str(content_base_file.uuid),
            )
            api_returned_at = _utc_now()
            document_status = result.get("document_status", "")
            if document_status in SUCCESS_STATUSES:
                break
            if _is_terminal_failure_status(document_status):
                last_exception = RuntimeError(f"Bedrock document status: {document_status}")
                break
            last_exception = RuntimeError(f"Unexpected Bedrock document status: {document_status}")
            break
        except ClientError as exc:
            api_returned_at = _utc_now()
            error_code = exc.response.get("Error", {}).get("Code", "")
            last_exception = exc
            log_ingestion_failed(
                {
                    "path": PATH_DIRECT,
                    "strategy": strategy,
                    "status": "fail",
                    "submitted_at": _iso(submitted_at),
                    "api_returned_at": _iso(api_returned_at),
                    "content_base_uuid": str(content_base_uuid),
                    "file_uuid": str(content_base_file.uuid),
                    "project_uuid": project_uuid,
                    "document_type": "file",
                    "exception_type": error_code,
                }
            )
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
        return False, PATH_JOB_FALLBACK

    task_manager_usecase.update_task_status(task_manager_uuid, TaskManager.STATUS_FAIL, "file")
    if last_exception and not isinstance(last_exception, ClientError):
        log_ingestion_failed(
            {
                "path": PATH_DIRECT,
                "strategy": strategy,
                "status": "fail",
                "submitted_at": _iso(submitted_at),
                "api_returned_at": _iso(api_returned_at),
                "final_status_at": _iso(final_status_at),
                "content_base_uuid": str(content_base_uuid),
                "file_uuid": str(content_base_file.uuid),
                "project_uuid": project_uuid,
                "document_type": "file",
                "exception_type": type(last_exception).__name__,
                "bedrock_document_status": document_status or None,
            }
        )
    return False, PATH_DIRECT
