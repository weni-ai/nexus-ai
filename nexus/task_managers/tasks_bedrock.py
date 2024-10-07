import pickle
from time import sleep
from typing import List

from botocore.exceptions import ClientError

from nexus.celery import app

from nexus.task_managers.models import ContentBaseFileTaskManager, TaskManager
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase

from nexus.usecases.intelligences.intelligences_dto import UpdateContentBaseFileDTO
from nexus.usecases.intelligences.update import UpdateContentBaseFileUseCase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase


@app.task
def check_ingestion_job_status(celery_task_manager_uuid: str, ingestion_job_id: str, waiting_time: int = 10, file_type: str = "file"):

    if waiting_time:
        sleep(waiting_time)

    print(f"[+ 🦑 BEDROCK: Checking Ingestion Job {ingestion_job_id} Status +]")

    file_database = BedrockFileDatabase()
    ingestion_job_status: str = file_database.get_bedrock_ingestion_status(ingestion_job_id)
    status = TaskManager.status_map.get(ingestion_job_status)

    task_manager_usecase = CeleryTaskManagerUseCase()
    task_manager_usecase.update_task_status(celery_task_manager_uuid, status, file_type)

    print(f"[+ 🦑 BEDROCK: Ingestion Job {ingestion_job_id} Status: {status} +]")

    if ingestion_job_status not in ["COMPLETE", "FAILED"]:
        check_ingestion_job_status.delay(celery_task_manager_uuid, ingestion_job_id)

    return True


@app.task
def start_ingestion_job(celery_task_manager_uuid: str, file_type: str = "file"):
    try:
        print("[+ 🦑 BEDROCK: Starting Ingestion Job +]")

        file_database = BedrockFileDatabase()
        in_progress_ingestion_jobs: List = file_database.list_bedrock_ingestion()

        if in_progress_ingestion_jobs:
            sleep(5)
            return start_ingestion_job(celery_task_manager_uuid)

        ingestion_job_id: str = file_database.start_bedrock_ingestion()

        # TODO: USECASE
        task_manager_usecase = CeleryTaskManagerUseCase()
        task_manager = task_manager_usecase.get_task_manager_by_uuid(celery_task_manager_uuid, file_type)
        task_manager.ingestion_job_id = ingestion_job_id
        task_manager.save()

        status = TaskManager.status_map.get("IN_PROGRESS")
        task_manager_usecase.update_task_status(celery_task_manager_uuid, status, file_type)
        check_ingestion_job_status.delay(celery_task_manager_uuid, ingestion_job_id)

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print("[+ 🦑 BEDROCK: Filter didn't catch in progress Ingestion Job. \n Waiting to start new IngestionJob ... +]")
            sleep(15)
            return start_ingestion_job(celery_task_manager_uuid)


@app.task
def bedrock_upload_file(
    file: bytes,
    content_base_uuid: str,
    user_email: str,
    content_base_file_uuid: str,
):
    print("[+ BEDROCK: Task to Upload File +]")
    file = pickle.loads(file)
    file_database = BedrockFileDatabase()
    file_database_response = file_database.add_file(file, content_base_uuid, content_base_file_uuid)

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }

    print("[+ File was added +]")

    content_base_file_dto = UpdateContentBaseFileDTO(
        file_url=file_database_response.file_url,
        file_name=file_database_response.file_name
    )
    content_base_file = UpdateContentBaseFileUseCase().update_content_base_file(
        content_base_file_uuid=content_base_file_uuid,
        user_email=user_email,
        update_content_base_file_dto=content_base_file_dto
    )
    task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(
        content_base_file=content_base_file
    )

    start_ingestion_job(str(task_manager.uuid))

    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base": {
            "uuid": content_base_file.uuid,
            "extension_file": content_base_file.extension_file,
        }
    }
    return response
