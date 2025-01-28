import pickle
from time import sleep
from typing import List, Dict

from botocore.exceptions import ClientError

from nexus.celery import app

from nexus.task_managers.models import ContentBaseFileTaskManager, TaskManager
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase

from nexus.intelligences.models import ContentBaseText, ContentBaseLink

from nexus.usecases.intelligences.intelligences_dto import UpdateContentBaseFileDTO
from nexus.usecases.intelligences.update import UpdateContentBaseFileUseCase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase

from langchain_community.document_loaders import AsyncChromiumLoader
from langchain_community.document_transformers import Html2TextTransformer


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
        check_ingestion_job_status.delay(celery_task_manager_uuid, ingestion_job_id, file_type=file_type)

    return True


@app.task
def start_ingestion_job(celery_task_manager_uuid: str, file_type: str = "file", post_delete: bool = False):
    try:
        print("[+ 🦑 BEDROCK: Starting Ingestion Job +]")

        file_database = BedrockFileDatabase()
        in_progress_ingestion_jobs: List = file_database.list_bedrock_ingestion()

        if in_progress_ingestion_jobs:
            sleep(5)
            return start_ingestion_job.delay(celery_task_manager_uuid, file_type=file_type)

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
        return check_ingestion_job_status.delay(celery_task_manager_uuid, ingestion_job_id, file_type=file_type)

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            print("[+ 🦑 BEDROCK: Filter didn't catch in progress Ingestion Job. \n Waiting to start new IngestionJob ... +]")
            sleep(15)
            return start_ingestion_job.delay(celery_task_manager_uuid, file_type=file_type)


@app.task
def bedrock_upload_file(
    file: bytes,
    content_base_uuid: str,
    user_email: str,
    content_base_file_uuid: str,
):
    print("[+ 🦑 BEDROCK: Task to Upload File +]")

    file = pickle.loads(file)

    file_database = BedrockFileDatabase()
    file_database_response = file_database.add_file(file, content_base_uuid, content_base_file_uuid)

    if file_database_response.status != 0:
        file_database.delete_file_and_metadata(content_base_uuid, file_database_response.file_name)
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }

    print("[+ 🦑 BEDROCK: File was added +]")

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


def create_txt_from_text(text, content_base_dto) -> str:
    content_base_title = content_base_dto.get('title', '').replace("/", "-").replace(" ", "-")
    file_name = f"{content_base_title}.txt"
    with open(f"/tmp/{file_name}", "w") as file:
        file.write(text)
    return file_name


@app.task
def bedrock_upload_text_file(text: str, content_base_dto: Dict, content_base_text_uuid: Dict):
    print(content_base_dto)
    file_name = create_txt_from_text(text, content_base_dto)
    content_base_uuid = str(content_base_dto.get("uuid"))
    file_database = BedrockFileDatabase()

    with open(f"/tmp/{file_name}", "rb") as file:
        file_database_response = file_database.add_file(file, content_base_uuid, content_base_text_uuid)

    # TODO: USECASE
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

    print("[+ 🦑 BEDROCK: Text File was added +}")

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
    print("[+ 🦑 BEDROCK: Task to Upload Link +]")
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

    print("[+ 🦑 BEDROCK: Link File was added +}")
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


@app.task
def run_create_lambda_function(
    lambda_name: str,
    agent_external_id: str,
    zip_content: bytes,
    agent_version: str,
    file_database=BedrockFileDatabase,
    function_schema: List[Dict] = []
):
    return file_database().create_lambda_function(
        lambda_name=lambda_name,
        agent_external_id=agent_external_id,
        agent_version=agent_version,
        source_code_file=zip_content,
        function_schema=function_schema,
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
    print(" UPDATE LAMBDA FUNCTION CODE ...")
    lambda_response = bedrock_client.update_lambda_function(
        lambda_name=lambda_name,
        zip_content=zip_content,
    )

    return lambda_response
