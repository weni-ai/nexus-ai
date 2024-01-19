import pickle
from nexus.celery import app

from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO


@app.task
def add_file(task_manager_uuid, type) -> bool:
    try:
        task_manager = CeleryTaskManagerUseCase().get_task_manager_by_uuid(task_uuid=task_manager_uuid)
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_LOADING)
    except Exception:
        return False

    sentenx_file_database = SentenXFileDataBase()
    if type == 'text':
        status_code, sentenx_response = sentenx_file_database.add_text_file(task_manager)
    else:
        status_code, sentenx_response = sentenx_file_database.add_file(task_manager)

    if status_code == 200:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_SUCCESS)
        return True

    task_manager.update_status(ContentBaseFileTaskManager.STATUS_FAIL)
    return False


@app.task
def upload_file(file: bytes, content_base_uuid: str, extension_file: str, user_email: str):
    from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase

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
    from nexus.usecases.intelligences.create import CreateContentBaseTextUseCase
    content_base_text = CreateContentBaseTextUseCase().create_contentbasetext(contentbase_uuid=content_base_uuid, user_email=user_email, text=text)
    with open(f"/tmp/{content_base_text.content_base.title}.txt", "w") as file:
        file.write(text)

    with open(f"/tmp/{content_base_text.content_base.title}.txt", "rb") as file:
        file_database_response = s3FileDatabase().add_file(file)


    if file_database_response.status != 0:
        return {
            "task_status": ContentBaseFileTaskManager.STATUS_FAIL,
            "error": file_database_response.err
        }

    task_manager = CeleryTaskManagerUseCase().create_celery_text_file_manager(content_base_text=content_base_text)
    print("[++++] PASSOU POR AQUI", task_manager)
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
