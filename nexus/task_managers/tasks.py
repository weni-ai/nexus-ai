import logging
from typing import Dict

import redis
from django.conf import settings

from nexus.celery import app
from nexus.intelligences.models import (
    ContentBaseLink,
    ContentBaseLogs,
    ContentBaseText,
    UserQuestion,
)
from nexus.logs.healthcheck import ClassificationHealthCheck, HealthCheck
from nexus.reports.flows_report.generate_output import main as get_flows_report
from nexus.storage import DeleteStorageFile
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.task_managers.file_database.sentenx_file_database import (
    SentenXFileDataBase,
)
from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.usecases.intelligences.get_by_uuid import get_by_contentbase_uuid
from nexus.usecases.intelligences.intelligences_dto import (
    UpdateContentBaseFileDTO,
)
from nexus.usecases.intelligences.update import UpdateContentBaseFileUseCase
from nexus.usecases.logs.delete import DeleteLogUsecase
from nexus.usecases.task_managers.celery_task_manager import (
    CeleryTaskManagerUseCase,
)

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = 60 * 60
REDIS_CLIENT = redis.Redis.from_url(settings.REDIS_URL)


@app.task
def add_file(task_manager_uuid: str, file_type: str, load_type: str = None) -> bool:
    try:
        task_manager = CeleryTaskManagerUseCase().get_task_manager_by_uuid(
            task_uuid=task_manager_uuid, file_type=file_type
        )
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_LOADING)
    except Exception as err:
        logger.error("Error updating task manager status: %s", err, exc_info=True)
        return False

    file_database = s3FileDatabase()
    sentenx_file_database = SentenXFileDataBase()

    if file_type == "text":
        status_code, _ = sentenx_file_database.add_text_file(task_manager, file_database)
    elif file_type == "link":
        status_code, _ = sentenx_file_database.add_link(task_manager, file_database)
    else:
        status_code, _ = sentenx_file_database.add_file(task_manager, file_database, load_type)

    if status_code == 200:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_SUCCESS)
        return True

    task_manager.update_status(ContentBaseFileTaskManager.STATUS_FAIL)
    return False


@app.task
def upload_file(
    file: bytes,
    content_base_uuid: str,
    extension_file: str,
    user_email: str,
    content_base_file_uuid: str,
    load_type: str = None,
    filename: str = None,
):
    file_database_response = s3FileDatabase().add_file(file, filename)

    if file_database_response.status != 0:
        return {"task_status": ContentBaseFileTaskManager.STATUS_FAIL, "error": file_database_response.err}

    content_base_file_dto = UpdateContentBaseFileDTO(
        file_url=file_database_response.file_url, file_name=file_database_response.file_name
    )

    content_base_file = UpdateContentBaseFileUseCase().update_content_base_file(
        content_base_file_uuid=content_base_file_uuid,
        user_email=user_email,
        update_content_base_file_dto=content_base_file_dto,
    )

    task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)

    add_file.apply_async(args=[str(task_manager.uuid), "file", load_type])
    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base": {
            "uuid": content_base_file.uuid,
            "extension_file": content_base_file.extension_file,
        },
    }
    return response


@app.task
def upload_sentenx_inline_file(
    file: bytes,
    content_base_uuid: str,
    extension_file: str,
    user_email: str,
    content_base_file_uuid: str,
    load_type: str = None,
    filename: str = None,
):
    file_database_response = s3FileDatabase().add_file(file, filename)

    if file_database_response.status != 0:
        return {"task_status": ContentBaseFileTaskManager.STATUS_FAIL, "error": file_database_response.err}

    content_base_file_dto = UpdateContentBaseFileDTO(
        file_url=file_database_response.file_url, file_name=file_database_response.file_name
    )

    content_base_file = UpdateContentBaseFileUseCase().update_inline_content_base_file(
        content_base_file_uuid=content_base_file_uuid,
        user_email=user_email,
        update_content_base_file_dto=content_base_file_dto,
    )

    task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)

    add_file.apply_async(args=[str(task_manager.uuid), "file", load_type])
    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base": {
            "uuid": content_base_file.uuid,
            "extension_file": content_base_file.extension_file,
        },
    }
    return response


@app.task
def upload_text_file(text: str, content_base_dto: Dict, content_base_text_uuid: Dict):
    content_base_title = content_base_dto.get("title", "").replace("/", "-").replace(" ", "-")
    file_name = f"{content_base_title}.txt"

    with open(f"/tmp/{file_name}", "w") as file:
        file.write(text)

    with open(f"/tmp/{file_name}", "rb") as file:
        file_database_response = s3FileDatabase().add_file(file, file_name)

    content_base_text = ContentBaseText.objects.get(uuid=content_base_text_uuid)
    content_base_text.file = file_database_response.file_url
    content_base_text.file_name = file_database_response.file_name
    content_base_text.save(update_fields=["file", "file_name"])

    if file_database_response.status != 0:
        return {"task_status": ContentBaseFileTaskManager.STATUS_FAIL, "error": file_database_response.err}

    task_manager = CeleryTaskManagerUseCase().create_celery_text_file_manager(content_base_text=content_base_text)
    add_file.apply_async(args=[str(task_manager.uuid), "text"])
    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base_text": {
            "uuid": content_base_text.uuid,
            "extension_file": "txt",
            "text": content_base_text.text,
        },
    }
    return response


@app.task
def send_link(link: str, user_email: str, content_base_link_uuid: str):
    content_base_link = ContentBaseLink.objects.get(uuid=content_base_link_uuid)
    task_manager = CeleryTaskManagerUseCase().create_celery_link_manager(content_base_link=content_base_link)
    add_file.apply_async(args=[str(task_manager.uuid), "link"])
    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base_text": {
            "uuid": content_base_link.uuid,
            "extension_file": "url",
            "link": content_base_link.link,
        },
    }
    return response


@app.task(name="create_wenigpt_logs")
def create_wenigpt_logs(log: Dict):
    try:
        content_base = get_by_contentbase_uuid(log.get("content_base_uuid"))
        log = ContentBaseLogs.objects.create(
            content_base=content_base,
            question=log.get("question"),
            language=log.get("language"),
            texts_chunks=log.get("texts_chunks"),
            full_prompt=log.get("full_prompt"),
            weni_gpt_response=log.get("weni_gpt_response"),
            wenigpt_version=settings.WENIGPT_VERSION,
        )
        UserQuestion.objects.create(text=log.question, content_base_log=log)
        logger.info("Creating log")
        return log
    except Exception as e:
        logger.error("Error creating log: %s", e, exc_info=True)
        return False


@app.task(name="log_cleanup_routine")
def log_cleanup_routine():
    usecase = DeleteLogUsecase()
    usecase.delete_logs_routine(months=1)


@app.task(name="delete_old_activities")
def delete_old_activities():
    usecase = DeleteLogUsecase()
    usecase.delete_old_activities(months=3)


@app.task(name="healthcheck")
def update_healthcheck():
    notify = HealthCheck()
    notify.check_service_health()


@app.task(name="classification_healthcheck")
def update_classification_healthcheck():
    classification_notify = ClassificationHealthCheck()
    classification_notify.check_service_health()


@app.task(name="cleanup_celery_reply_channels")
def cleanup_celery_reply_channels():
    """
    Clean up Celery control API reply channels that accumulate without TTL.

    These are created when using app.control.revoke() or other control API calls.
    Runs every 12 hours to prevent memory accumulation from task revocations.
    """
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        cursor = 0
        deleted = 0
        total_size = 0

        while True:
            cursor, keys = redis_client.scan(cursor, match="*.reply.celery.pidbox", count=1000)
            for key in keys:
                try:
                    size = redis_client.memory_usage(key) or 0
                    redis_client.delete(key)
                    deleted += 1
                    total_size += size
                except Exception as e:
                    logger.warning(f"Error deleting Celery reply channel {key}: {e}")

            if cursor == 0:
                break

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} Celery reply channels, freed {total_size / (1024*1024):.2f} MB")
    except Exception as e:
        logger.error(f"Error cleaning up Celery reply channels: {e}", exc_info=True)


@app.task(name="delete_attachment_preview_file")
def delete_file_task(file_name):
    deleter = DeleteStorageFile()
    deleter.delete_file(file_name)


@app.task(
    name="generate_flows_report",
    soft_time_limit=7000,
    time_limit=7200,
)
def generate_flows_report(auth_token: str, start_date: str = None, end_date: str = None):
    alt_lock_key = "generate_flows_report_lock"
    lock_id = f"task_lock:{alt_lock_key}"

    lock_acquired = REDIS_CLIENT.set(lock_id, "true", ex=LOCK_TIMEOUT, nx=True)

    if not lock_acquired:
        logger.info("Task generate_flows_report is already running. Skipping this execution.")
        return False
    try:
        logger.info("Starting generate_flows_report")
        result = get_flows_report(auth_token, start_date, end_date)
        logger.info("generate_flows_report completed successfully")
        return result
    finally:
        REDIS_CLIENT.delete(lock_id)
        logger.info("Lock released for generate_flows_report")
