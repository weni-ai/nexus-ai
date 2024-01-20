import pickle
from nexus.celery import app

from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase
from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO, ContentBaseDTO, ContentBaseTextDTO
from nexus.usecases.intelligences.create import CreateContentBaseTextUseCase
from nexus.usecases.intelligences.retrieve import RetrieveContentBaseUseCase


@app.task
def add_file(task_manager_uuid: str, file_type: str) -> bool:
    try:
        task_manager = CeleryTaskManagerUseCase().get_task_manager_by_uuid(task_uuid=task_manager_uuid, file_type=file_type)
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_LOADING)
    except Exception as err:
        print(err)
        return False

    file_database = s3FileDatabase()
    sentenx_file_database = SentenXFileDataBase()

    if type == 'text':
        status_code, _ = sentenx_file_database.add_text_file(task_manager, file_database)
    else:
        status_code, _ = sentenx_file_database.add_file(task_manager, file_database)
    if status_code == 200:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_SUCCESS)
        return True

    task_manager.update_status(ContentBaseFileTaskManager.STATUS_FAIL)
    return False


@app.task
def upload_file(file: bytes, content_base_uuid: str, extension_file: str, user_email: str):
    file = pickle.loads(file)
    file_database_response = s3FileDatabase().add_file(file)

    if file_database_response.status != 0:
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }

    content_base_file_dto = ContentBaseFileDTO(
        file=file,
        user_email=user_email,
        content_base_uuid=content_base_uuid,
        extension_file=extension_file,
        file_url=file_database_response.file_url,
        file_name=file_database_response.file_name
    )

    content_base_file = CreateContentBaseFileUseCase().create_content_base_file(content_base_file=content_base_file_dto)
    task_manager = CeleryTaskManagerUseCase().create_celery_task_manager(content_base_file=content_base_file)

    add_file.apply_async(args=[str(task_manager.uuid), "file"])
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
def upload_text_file(text: str, content_base_uuid: str, user_email: str):

    content_base = RetrieveContentBaseUseCase().get_contentbase(content_base_uuid, user_email)

    content_base_dto = ContentBaseDTO(
        uuid=str(content_base.uuid),
        title=content_base.title,
        intelligence_uuid=str(content_base.intelligence.uuid),
        created_by_email=user_email
    )

    file_name = f"{content_base_dto.title}.txt"

    with open(f"/tmp/{file_name}", "w") as file:
        file.write(text)

    with open(f"/tmp/{file_name}", "rb") as file:
        file_database_response = s3FileDatabase().add_file(file)

    content_base_text_dto = ContentBaseTextDTO(
        file=file_database_response.file_url,
        file_name=file_database_response.file_name,
        text=text,
        content_base_uuid=content_base_dto.uuid,
        user_email=content_base_dto.created_by_email
    )

    content_base_text = CreateContentBaseTextUseCase().create_contentbasetext(
        content_base_dto=content_base_dto,
        content_base_text_dto=content_base_text_dto
    )

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
        "content_base": {
            "uuid": content_base_text.uuid,
            "extension_file": 'txt',
        }
    }
    return response
