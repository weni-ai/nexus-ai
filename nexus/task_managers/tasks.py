import pickle
from nexus.celery import app

from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.task_managers.models import ContentBaseFileTaskManager
from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.usecases.intelligences.intelligences_dto import ContentBaseFileDTO
from nexus.usecases.intelligences.create import CreateContentBaseFileUseCase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase


@app.task
def add_file(task_manager_uuid):
    try:
        task_manager = CeleryTaskManagerUseCase().get_task_manager_by_uuid(task_uuid=task_manager_uuid)
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_LOADING)
        print(f"[ ADD FILE ] - updated status from task {task_manager.uuid}")
    except Exception as exception:
        print(f"[ ADD FILE ] - error: {exception}")
        return
    sentenx_file_database = SentenXFileDataBase()
    print("[ ADD FILE ]", type(task_manager))
    print("[ ADD FILE ]", task_manager.__dict__)
    status_code, sentenx_response = sentenx_file_database.add_file(task_manager)
    if status_code == 200:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_SUCCESS)
        print(f"ADD FILE TASK ] - success on index new file `{task_manager.content_base_file.uuid}`")
    else:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_FAIL)
        print("[ ADD FILE TASK ] - fail on index file in sentenx")


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

    print(f"[ FILEMANAGER] task_manager: {task_manager.uuid}")
    add_file.apply_async(args=[str(task_manager.uuid)])
    response = {
        "task_uuid": task_manager.uuid,
        "task_status": task_manager.status,
        "content_base": {
            "uuid": content_base_file.uuid,
            "extension_file": content_base_file.extension_file,
        }
    }
    return response
