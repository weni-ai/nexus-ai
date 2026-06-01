import logging
from time import sleep
from typing import Dict, List, Optional

from botocore.exceptions import ClientError
from django.conf import settings
from langchain_community.document_loaders import AsyncChromiumLoader
from langchain_community.document_transformers import Html2TextTransformer

from nexus.agents.models import Agent
from nexus.celery import app
from nexus.intelligences.models import ContentBaseLink, ContentBaseText
from nexus.projects.models import Project
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.task_managers.models import ContentBaseFileTaskManager, TaskManager
from nexus.usecases.intelligences.intelligences_dto import UpdateContentBaseFileDTO
from nexus.usecases.intelligences.update import UpdateContentBaseFileUseCase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase

logger = logging.getLogger(__name__)

DIRECT_INGEST_SUCCESS_STATUS = "INDEXED"
DIRECT_INGEST_FAILED_STATUSES = {
    "FAILED",
    "METADATA_UPDATE_FAILED",
    "METADATA_PARTIALLY_INDEXED",
    "PARTIALLY_INDEXED",
    "IGNORED",
    "NOT_FOUND",
}
DIRECT_INGEST_IN_PROGRESS_STATUSES = {"STARTING", "PENDING", "IN_PROGRESS"}


def _get_task_manager_content_info(task_manager, file_type: str) -> tuple[str | None, str | None]:
    if hasattr(task_manager, "content_base_file") and task_manager.content_base_file:
        return (
            str(task_manager.content_base_file.content_base.uuid),
            task_manager.content_base_file.file_name,
        )
    if hasattr(task_manager, "content_base_text") and task_manager.content_base_text:
        return (
            str(task_manager.content_base_text.content_base.uuid),
            task_manager.content_base_text.file_name,
        )
    if hasattr(task_manager, "content_base_link") and task_manager.content_base_link:
        return (
            str(task_manager.content_base_link.content_base.uuid),
            task_manager.content_base_link.name,
        )
    logger.error(
        "🦑 BEDROCK: Could not determine content info - task_manager em estado inválido",
        extra={"file_type": file_type, "task_manager_type": type(task_manager).__name__},
    )
    return None, None


@app.task
def check_ingestion_job_status(
    celery_task_manager_uuid: str,
    ingestion_job_id: str,
    waiting_time: int = 10,
    file_type: str = "file",
    project_uuid: str | None = None,
):
    if waiting_time:
        sleep(waiting_time)

    logger.info(f"🦑 BEDROCK: Checking Ingestion Job {ingestion_job_id} Status")

    file_database = BedrockFileDatabase(project_uuid=project_uuid)
    ingestion_job_status: str = file_database.get_bedrock_ingestion_status(ingestion_job_id)
    status = TaskManager.status_map.get(ingestion_job_status)

    task_manager_usecase = CeleryTaskManagerUseCase()

    logger.info(f"🦑 BEDROCK: Ingestion Job {ingestion_job_id} Status: {ingestion_job_status}")

    if ingestion_job_status not in ["COMPLETE", "FAILED"]:
        task_manager_usecase.update_task_status(celery_task_manager_uuid, status, file_type)
        check_ingestion_job_status.delay(
            celery_task_manager_uuid, ingestion_job_id, file_type=file_type, project_uuid=project_uuid
        )
    elif ingestion_job_status == "COMPLETE":
        try:
            task_manager = task_manager_usecase.get_task_manager_by_uuid(celery_task_manager_uuid, file_type)

            content_base_uuid, _ = _get_task_manager_content_info(task_manager, file_type)
            if not content_base_uuid:
                return True

            file_database.search_data(content_base_uuid=content_base_uuid, text="test", number_of_results=1)
            logger.info(
                f"🦑 BEDROCK: Knowledge base is accessible for content_base_uuid "
                f"{content_base_uuid}, marking as success"
            )
            task_manager_usecase.update_task_status(celery_task_manager_uuid, status, file_type)

        except Exception as e:
            logger.warning(f"🦑 BEDROCK: Knowledge base not yet accessible or data not indexed, will retry. Error: {e}")
            processing_status = TaskManager.status_map.get("IN_PROGRESS")
            task_manager_usecase.update_task_status(celery_task_manager_uuid, processing_status, file_type)
            check_ingestion_job_status.delay(
                celery_task_manager_uuid,
                ingestion_job_id,
                waiting_time=30,
                file_type=file_type,
                project_uuid=project_uuid,
            )
    elif ingestion_job_status == "FAILED":
        task_manager_usecase.update_task_status(celery_task_manager_uuid, status, file_type)

    return True


@app.task
def direct_ingest(
    celery_task_manager_uuid: str,
    file_type: str = "file",
    project_uuid: str | None = None,
    waiting_time: int = 0,
):
    if waiting_time:
        sleep(waiting_time)

    logger.info("🦑 BEDROCK: Direct ingesting document")

    task_manager_usecase = CeleryTaskManagerUseCase()
    task_manager = task_manager_usecase.get_task_manager_by_uuid(celery_task_manager_uuid, file_type)
    content_base_uuid, filename = _get_task_manager_content_info(task_manager, file_type)

    if not content_base_uuid or not filename:
        task_manager_usecase.update_task_status(celery_task_manager_uuid, TaskManager.STATUS_FAIL, file_type)
        return True

    file_database = BedrockFileDatabase(project_uuid=project_uuid)
    document_details = file_database.direct_ingest(content_base_uuid, filename)
    doc_status = document_details[0].get("status") if document_details else None

    logger.info(f"🦑 BEDROCK: Direct ingest document status: {doc_status}")

    if doc_status in DIRECT_INGEST_FAILED_STATUSES:
        task_manager_usecase.update_task_status(celery_task_manager_uuid, TaskManager.STATUS_FAIL, file_type)
        return True

    if doc_status in DIRECT_INGEST_IN_PROGRESS_STATUSES or doc_status is None:
        processing_status = TaskManager.status_map.get("IN_PROGRESS")
        task_manager_usecase.update_task_status(celery_task_manager_uuid, processing_status, file_type)
        direct_ingest.delay(
            celery_task_manager_uuid,
            file_type=file_type,
            project_uuid=project_uuid,
            waiting_time=30,
        )
        return True

    if doc_status == DIRECT_INGEST_SUCCESS_STATUS:
        try:
            file_database.search_data(content_base_uuid=content_base_uuid, text="test", number_of_results=1)
            logger.info(
                f"🦑 BEDROCK: Knowledge base is accessible for content_base_uuid "
                f"{content_base_uuid}, marking as success"
            )
            task_manager_usecase.update_task_status(
                celery_task_manager_uuid, TaskManager.status_map.get("COMPLETE"), file_type
            )
        except Exception as e:
            logger.warning(f"🦑 BEDROCK: Document indexed but not yet searchable, will retry. Error: {e}")
            processing_status = TaskManager.status_map.get("IN_PROGRESS")
            task_manager_usecase.update_task_status(celery_task_manager_uuid, processing_status, file_type)
            direct_ingest.delay(
                celery_task_manager_uuid,
                file_type=file_type,
                project_uuid=project_uuid,
                waiting_time=30,
            )
        return True

    logger.warning(f"🦑 BEDROCK: Unknown direct ingest status: {doc_status}")
    task_manager_usecase.update_task_status(celery_task_manager_uuid, TaskManager.STATUS_FAIL, file_type)
    return True


@app.task
def direct_delete(content_base_uuid: str, filename: str, project_uuid: str | None = None):
    logger.info("🦑 BEDROCK: Direct deleting document from knowledge base")
    file_database = BedrockFileDatabase(project_uuid=project_uuid)
    file_database.direct_delete(content_base_uuid, filename)
    return True


@app.task
def trigger_bedrock_ingestion(
    celery_task_manager_uuid: str,
    file_type: str = "file",
    post_delete: bool = False,
    project_uuid: str | None = None,
    content_base_uuid: str | None = None,
    filename: str | None = None,
):
    strategy = Project.BEDROCK_INGESTION_JOB
    if project_uuid:
        try:
            project = Project.objects.get(uuid=project_uuid)
            strategy = project.bedrock_ingestion_strategy
        except Project.DoesNotExist:
            logger.warning(f"🦑 BEDROCK: Project {project_uuid} not found, using default ingestion strategy")

    if strategy == Project.BEDROCK_INGESTION_DIRECT:
        if post_delete:
            if content_base_uuid and filename:
                return direct_delete.delay(content_base_uuid, filename, project_uuid)
            logger.warning("🦑 BEDROCK: Direct delete missing content_base_uuid or filename, skipping")
            return
        return direct_ingest.delay(celery_task_manager_uuid, file_type=file_type, project_uuid=project_uuid)

    return start_ingestion_job(
        celery_task_manager_uuid, file_type=file_type, post_delete=post_delete, project_uuid=project_uuid
    )


@app.task
def start_ingestion_job(
    celery_task_manager_uuid: str, file_type: str = "file", post_delete: bool = False, project_uuid: str | None = None
):
    if not settings.BEDROCK_INGESTION_JOB_ENABLED:
        logger.warning("🦑 BEDROCK: Ingestion job disabled via BEDROCK_INGESTION_JOB_ENABLED")
        if post_delete or not celery_task_manager_uuid:
            return
        CeleryTaskManagerUseCase().update_task_status(celery_task_manager_uuid, TaskManager.STATUS_FAIL, file_type)
        return

    try:
        logger.info("🦑 BEDROCK: Starting Ingestion Job")

        file_database = BedrockFileDatabase(project_uuid=project_uuid)
        in_progress_ingestion_jobs: List = file_database.list_bedrock_ingestion()

        if in_progress_ingestion_jobs:
            sleep(5)
            return start_ingestion_job.delay(celery_task_manager_uuid, file_type=file_type, project_uuid=project_uuid)

        ingestion_job_id: str = file_database.start_bedrock_ingestion()

        if post_delete:
            return

        # TODO: USECASE
        task_manager_usecase = CeleryTaskManagerUseCase()
        task_manager = task_manager_usecase.get_task_manager_by_uuid(celery_task_manager_uuid, file_type)
        task_manager.ingestion_job_id = ingestion_job_id
        task_manager.save()

        status = TaskManager.status_map.get("IN_PROGRESS")
        task_manager_usecase.update_task_status(celery_task_manager_uuid, status, file_type)
        return check_ingestion_job_status.delay(
            celery_task_manager_uuid, ingestion_job_id, file_type=file_type, project_uuid=project_uuid
        )

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            logger.warning(
                "🦑 BEDROCK: Filter didn't catch in progress Ingestion Job. " "Waiting to start new IngestionJob ..."
            )
            sleep(15)
            return start_ingestion_job.delay(celery_task_manager_uuid, file_type=file_type, project_uuid=project_uuid)


@app.task
def bedrock_upload_file(
    file: bytes, content_base_uuid: str, user_email: str, content_base_file_uuid: str, filename: str
):
    from nexus.usecases.projects.projects_use_case import ProjectsUseCase

    project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
    logger.info("🦑 BEDROCK: Task to Upload File")

    file_database = BedrockFileDatabase(project_uuid=str(project.uuid))
    file_database_response = file_database.add_file(file, content_base_uuid, content_base_file_uuid)

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {"task_status": ContentBaseFileTaskManager.STATUS_FAIL, "error": file_database_response.err}

    logger.info("🦑 BEDROCK: File was added")

    content_base_file_dto = UpdateContentBaseFileDTO(
        file_url=file_database_response.file_url, file_name=file_database_response.file_name
    )
    content_base_file = UpdateContentBaseFileUseCase().update_content_base_file(
        content_base_file_uuid=content_base_file_uuid,
        user_email=user_email,
        update_content_base_file_dto=content_base_file_dto,
    )
    task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)

    trigger_bedrock_ingestion(str(task_manager.uuid), project_uuid=str(project.uuid))

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
def bedrock_upload_inline_file(
    file: bytes, content_base_uuid: str, user_email: str, content_base_file_uuid: str, filename: str
):
    from nexus.usecases.projects.projects_use_case import ProjectsUseCase

    logger.info("🦑 BEDROCK: Task to Upload Inline File")

    project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
    file_database = BedrockFileDatabase(project_uuid=str(project.uuid))
    file_database_response = file_database.add_file(file, content_base_uuid, content_base_file_uuid)

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {"task_status": ContentBaseFileTaskManager.STATUS_FAIL, "error": file_database_response.err}

    logger.info("🦑 BEDROCK: Inline File was added")

    content_base_file_dto = UpdateContentBaseFileDTO(
        file_url=file_database_response.file_url, file_name=file_database_response.file_name
    )
    content_base_file = UpdateContentBaseFileUseCase().update_inline_content_base_file(
        content_base_file_uuid=content_base_file_uuid,
        user_email=user_email,
        update_content_base_file_dto=content_base_file_dto,
    )
    task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)

    trigger_bedrock_ingestion(str(task_manager.uuid), project_uuid=str(project.uuid))

    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base": {
            "uuid": content_base_file.uuid,
            "extension_file": content_base_file.extension_file,
        },
    }
    return response


def create_txt_from_text(text, content_base_dto) -> str:
    content_base_title = content_base_dto.get("title", "").replace("/", "-").replace(" ", "-")
    file_name = f"{content_base_title}.txt"
    with open(f"/tmp/{file_name}", "w") as file:
        file.write(text)
    return file_name


@app.task
def bedrock_upload_text_file(text: str, content_base_dto: Dict, content_base_text_uuid: Dict):
    from nexus.usecases.projects.projects_use_case import ProjectsUseCase

    file_name = create_txt_from_text(text, content_base_dto)
    content_base_uuid = str(content_base_dto.get("uuid"))
    project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
    file_database = BedrockFileDatabase(project_uuid=str(project.uuid))

    content_base_text = ContentBaseText.objects.get(uuid=content_base_text_uuid)
    old_file_name = content_base_text.file_name

    with open(f"/tmp/{file_name}", "rb") as file:
        file_database_response = file_database.add_file(file, content_base_uuid, content_base_text_uuid)

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {"task_status": ContentBaseFileTaskManager.STATUS_FAIL, "error": file_database_response.err}

    logger.info("🦑 BEDROCK: Text File was added")

    content_base_text.file = file_database_response.file_url
    content_base_text.file_name = file_database_response.file_name
    content_base_text.save(update_fields=["file", "file_name"])

    if old_file_name:
        file_database.delete_file_and_metadata(content_base_uuid, old_file_name)

    task_manager = CeleryTaskManagerUseCase().create_celery_text_file_manager(content_base_text=content_base_text)
    trigger_bedrock_ingestion(str(task_manager.uuid), "text", project_uuid=str(project.uuid))

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


def url_to_markdown(link: str, link_uuid: str) -> str:
    """Transforms link content into Markdown and returns the filename"""
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
    from nexus.usecases.projects.projects_use_case import ProjectsUseCase

    logger.info("🦑 BEDROCK: Task to Upload Link")
    content_base_link = ContentBaseLink.objects.get(uuid=content_base_link_uuid)
    content_base_uuid = str(content_base_link.content_base.uuid)
    project = ProjectsUseCase().get_project_by_content_base_uuid(content_base_uuid)
    task_manager = CeleryTaskManagerUseCase().create_celery_link_manager(content_base_link=content_base_link)

    filename = url_to_markdown(link, str(content_base_link.uuid))

    file_database = BedrockFileDatabase(project_uuid=str(project.uuid))

    with open(f"/tmp/{filename}", "rb") as file:
        file_database_response = file_database.add_file(file, content_base_uuid, content_base_link_uuid)

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {"task_status": ContentBaseFileTaskManager.STATUS_FAIL, "error": file_database_response.err}

    # TODO: usecase
    content_base_link.name = file_database_response.file_name
    content_base_link.save(update_fields=["name"])

    logger.info("🦑 BEDROCK: Link File was added")
    trigger_bedrock_ingestion(str(task_manager.uuid), "link", project_uuid=str(project.uuid))

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


@app.task
def run_create_lambda_function(
    lambda_name: str,
    agent_external_id: str,
    zip_content: bytes,
    agent_version: str,
    skill_handler: str,
    agent: Agent,
    function_schema: Optional[List[Dict]] = None,
    file_database=BedrockFileDatabase,
):
    if function_schema is None:
        function_schema = []
    return file_database().create_lambda_function(
        lambda_name=lambda_name,
        agent_external_id=agent_external_id,
        agent_version=agent_version,
        source_code_file=zip_content,
        function_schema=function_schema,
        agent=agent,
        skill_handler=skill_handler,
    )


def run_update_lambda_function(
    agent_external_id: str,
    lambda_name: str,
    lambda_arn: str,
    agent_version: str,
    zip_content: bytes,
    function_schema: List[Dict],
):
    """
    Updates an existing Lambda function's code.

    Args:
        agent_external_id: External ID of the agent
        lambda_name: Name of the Lambda function
        lambda_arn: ARN of the Lambda function
        agent_version: Version of the agent
        zip_content: Function code in zip format
        function_schema: Schema defining the function interface
    """
    bedrock_client = BedrockFileDatabase()

    # Update the Lambda function code and its alias
    logger.info("UPDATE LAMBDA FUNCTION CODE ...")
    lambda_response = bedrock_client.update_lambda_function(
        lambda_name=lambda_name,
        zip_content=zip_content,
    )

    return lambda_response
