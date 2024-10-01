import pickle
import time
from typing import Dict, List

from botocore.exceptions import ClientError

from django.conf import settings

from nexus.celery import app

from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.task_managers.models import ContentBaseFileTaskManager, TaskManager
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase

from nexus.logs.healthcheck import HealthCheck, ClassificationHealthCheck
from nexus.intelligences.models import (
    ContentBaseText,
    ContentBaseLogs,
    ContentBaseLink,
    UserQuestion,
)

from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.usecases.intelligences.intelligences_dto import UpdateContentBaseFileDTO
from nexus.usecases.intelligences.update import UpdateContentBaseFileUseCase
from nexus.usecases.intelligences.get_by_uuid import get_by_contentbase_uuid
from nexus.usecases.logs.delete import DeleteLogUsecase

from nexus.trulens import wenigpt_evaluation, tru_recorder


@app.task
def add_file(
    task_manager_uuid: str,
    file_type: str,
    load_type: str = None
) -> bool:

    try:
        task_manager = CeleryTaskManagerUseCase().get_task_manager_by_uuid(task_uuid=task_manager_uuid, file_type=file_type)
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_LOADING)
    except Exception as err:
        print(err)
        return False

    file_database = s3FileDatabase()
    sentenx_file_database = SentenXFileDataBase()

    if file_type == 'text':
        status_code, _ = sentenx_file_database.add_text_file(task_manager, file_database)
    elif file_type == 'link':
        status_code, _ = sentenx_file_database.add_link(task_manager, file_database)
    else:
        status_code, _ = sentenx_file_database.add_file(task_manager, file_database, load_type)

    if status_code == 200:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_SUCCESS)
        return True

    task_manager.update_status(ContentBaseFileTaskManager.STATUS_FAIL)
    return False


@app.task
def check_ingestion_job_status(celery_task_manager_uuid: str, ingestion_job_id: str, waiting_time: int = 10, file_type: str = "file"):

    if waiting_time:
        time.sleep(waiting_time)

    print(f"[+ 🦑 Checking Ingestion Job {ingestion_job_id} Status +]")

    file_database = BedrockFileDatabase()
    ingestion_job_status: str = file_database.get_bedrock_ingestion_status(ingestion_job_id)
    status = TaskManager.status_map.get(ingestion_job_status)

    task_manager_usecase = CeleryTaskManagerUseCase()
    task_manager_usecase.update_task_status(celery_task_manager_uuid, status, file_type)

    print(f"[+ 🦑 Ingestion Job {ingestion_job_id} Status: {status} +]")

    if ingestion_job_status not in ["COMPLETE", "FAILED"]:
        check_ingestion_job_status.delay(celery_task_manager_uuid, ingestion_job_id)


@app.task
def start_ingestion_job(celery_task_manager_uuid: str, file_type: str = "file"):
    try:
        print("[+ 🦑 Starting Ingestion Job +]")

        file_database = BedrockFileDatabase()
        ingestion_jobs: List = file_database.list_bedrock_ingestion()

        if ingestion_jobs:
            time.sleep(5)
            return start_ingestion_job(celery_task_manager_uuid, file_type)

        ingestion_job_id: str = file_database.start_bedrock_ingestion()

        task_manager_usecase = CeleryTaskManagerUseCase()

        task_manager = task_manager_usecase.get_task_manager_by_uuid(celery_task_manager_uuid, file_type)
        task_manager.ingestion_job_id = ingestion_job_id
        task_manager.save()
        status = TaskManager.status_map.get("IN_PROGRESS")
        task_manager_usecase.update_task_status(celery_task_manager_uuid, status, file_type)
        check_ingestion_job_status.delay(celery_task_manager_uuid, ingestion_job_id, file_type=file_type)

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print("[+ Filter didn't catch in progress Ingestion Job. \n Waiting to start new IngestionJob ... +]")
            time.sleep(15)
            return start_ingestion_job(celery_task_manager_uuid, file_type)


@app.task
def bedrock_upload_file(
    file: bytes,
    content_base_uuid: str,
    user_email: str,
    content_base_file_uuid: str,
):
    print("[+ Task to Upload File to Bedrock +]")
    file = pickle.loads(file)
    file_database = BedrockFileDatabase()
    file_database_response = file_database.add_file(file, content_base_uuid, content_base_file_uuid)

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }

    print("[+ File was added +}")
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


@app.task
def upload_file(
    file: bytes,
    content_base_uuid: str,
    extension_file: str,
    user_email: str,
    content_base_file_uuid: str,
    load_type: str = None
):
    file = pickle.loads(file)
    file_database_response = s3FileDatabase().add_file(file)

    if file_database_response.status != 0:
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }

    content_base_file_dto = UpdateContentBaseFileDTO(
        file_url=file_database_response.file_url,
        file_name=file_database_response.file_name
    )

    content_base_file = UpdateContentBaseFileUseCase().update_content_base_file(
        content_base_file_uuid=content_base_file_uuid,
        user_email=user_email,
        update_content_base_file_dto=content_base_file_dto
    )

    task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)

    add_file.apply_async(args=[str(task_manager.uuid), "file", load_type])
    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base": {
            "uuid": content_base_file.uuid,
            "extension_file": content_base_file.extension_file,
        }
    }
    return response


def create_txt_from_text(text, content_base_dto) -> str:
    content_base_title = content_base_dto.get('title', '').replace("/", "-").replace(" ", "-")
    file_name = f"{content_base_title}.txt"
    with open(f"/tmp/{file_name}", "w") as file:
        file.write(text)
    return file_name


@app.task
def bedrock_upload_text_file(text: str, content_base_dto: Dict, content_base_text_uuid: Dict):
    file_name = create_txt_from_text(text, content_base_dto)
    content_base_uuid = str(content_base_dto.get("uuid"))
    file_database = BedrockFileDatabase()

    with open(f"/tmp/{file_name}", "rb") as file:
        file_database_response = file_database.add_file(file, content_base_uuid, content_base_text_uuid)

    # TODO: create usecase
    content_base_text = ContentBaseText.objects.get(uuid=content_base_text_uuid)
    content_base_text.file = file_database_response.file_url
    content_base_text.file_name = file_database_response.file_name
    content_base_text.save(update_fields=['file', 'file_name'])

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }

    print("[+ Text File was added +}")

    task_manager = CeleryTaskManagerUseCase().create_celery_text_file_manager(content_base_text=content_base_text)
    start_ingestion_job(str(task_manager.uuid), "text")

    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base_text": {
            "uuid": content_base_text.uuid,
            "extension_file": 'txt',
            "text": content_base_text.text,
        }
    }
    return response


@app.task
def upload_text_file(text: str, content_base_dto: Dict, content_base_text_uuid: Dict):
    content_base_title = content_base_dto.get('title', '').replace("/", "-").replace(" ", "-")
    file_name = f"{content_base_title}.txt"

    with open(f"/tmp/{file_name}", "w") as file:
        file.write(text)

    with open(f"/tmp/{file_name}", "rb") as file:
        file_database_response = s3FileDatabase().add_file(file)

    content_base_text = ContentBaseText.objects.get(uuid=content_base_text_uuid)
    content_base_text.file = file_database_response.file_url
    content_base_text.file_name = file_database_response.file_name
    content_base_text.save(update_fields=['file', 'file_name'])

    if file_database_response.status != 0:
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }

    task_manager = CeleryTaskManagerUseCase().create_celery_text_file_manager(content_base_text=content_base_text)
    add_file.apply_async(args=[str(task_manager.uuid), "text"])
    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base_text": {
            "uuid": content_base_text.uuid,
            "extension_file": 'txt',
            "text": content_base_text.text,
        }
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
            "extension_file": 'url',
            "link": content_base_link.link,
        }
    }
    return response

def url_to_markdown(link: str, link_uuid: str) -> str:
    from typing import List
    from langchain_community.document_loaders import AsyncChromiumLoader
    from langchain_community.document_transformers import Html2TextTransformer

    links: List[str] = [link]

    loader = AsyncChromiumLoader(links)
    docs = loader.load()

    html2text = Html2TextTransformer()
    docs_transformed = html2text.transform_documents(docs)

    filename = f"{link_uuid}.md"

    with open(f"/tmp/{filename}", "w") as file:
        file.write(docs_transformed[0].page_content)
    
    return filename


@app.task
def bedrock_send_link(link: str, user_email: str, content_base_link_uuid: str):
    content_base_link = ContentBaseLink.objects.get(uuid=content_base_link_uuid)
    content_base_uuid = str(content_base_link.content_base.uuid)
    task_manager = CeleryTaskManagerUseCase().create_celery_link_manager(content_base_link=content_base_link)

    filename = url_to_markdown(link, str(content_base_link.uuid))

    file_database = BedrockFileDatabase()

    with open(f"/tmp/{filename}", "rb") as file:
        file_database_response = file_database.add_file(file, content_base_uuid, content_base_link_uuid)

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }
    
    # TODO: usecase
    content_base_link.name = file_database_response.file_name
    content_base_link.save(update_fields=['name'])

    print("[+ Link File was added +}")

    task_manager = CeleryTaskManagerUseCase().create_celery_link_manager(content_base_link=content_base_link)
    start_ingestion_job(str(task_manager.uuid), "link")

    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base_text": {
            "uuid": content_base_link.uuid,
            "extension_file": 'url',
            "link": content_base_link.link,
        }
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
        UserQuestion.objects.create(
            text=log.question,
            content_base_log=log
        )
        print("[Creating Log]")
        trulens_evaluation.delay(log.id)
        return log
    except Exception as e:
        print(e)
        return False


@app.task(name="trulens_evaluation")
def trulens_evaluation(log_id: str):
    log = ContentBaseLogs.objects.get(id=log_id)
    with tru_recorder:
        wenigpt_evaluation.get_answer(log.question, log)
    return True


@app.task(name="log_cleanup_routine")
def log_cleanup_routine():
    usecase = DeleteLogUsecase()
    usecase.delete_logs_routine(months=1)


@app.task(name='delete_old_activities')
def delete_old_activities():
    usecase = DeleteLogUsecase()
    usecase.delete_old_activities(months=3)


@app.task(name='healthcheck')
def update_healthcheck():
    notify = HealthCheck()
    notify.check_service_health()


@app.task(name='classification_healthcheck')
def update_classification_healthcheck():
    classification_notify = ClassificationHealthCheck()
    classification_notify.check_service_health()
