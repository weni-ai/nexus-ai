from nexus.celery import app

from nexus.task_managers.file_database.s3_file_database import s3FileDatabase
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.usecases.task_managers.celery_task_manager import CeleryTaskManagerUseCase
from nexus.task_managers.models import ContentBaseFileTaskManager

@app.task
def add_file(task_manager_uuid, file):
    try:
        task_manager = CeleryTaskManagerUseCase().get_task_manager_by_uuid(task_uuid=task_manager_uuid)
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_LOADING)
        print(f"[ ADD FILE ] - updated status from task {task_manager.uuid}")
    except Exception as exception:
        print(f"[ ADD FILE ] - error: {exception}")
        return
    file_database = s3FileDatabase()
    response = file_database.add_file(file)
    if response.status == 0:
        task_manager.content_base_file.file_url = response.url
        task_manager.content_base_file.save(update_fields=["file_url"])
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_PROCESSING)
        print(f"[ ADD FILE TASK ] - success on add file to file database {task_manager.content_base_file.uuid}")
    else:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_FAIL)
        print("[ ADD FILE TASK ] - fail on add file to file database")
        return
    sentenx_file_database = SentenXFileDataBase()
    sentenx_response = sentenx_file_database.add_file(task_manager)
    if sentenx_response.status_code == 200:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_SUCCESS)
        print(f"ADD FILE TASK ] - success on index new file `{task_manager.content_base_file.uuid}`")
    else:
        task_manager.update_status(ContentBaseFileTaskManager.STATUS_FAIL)
        print("[ ADD FILE TASK ] - fail on index file in sentenx")
