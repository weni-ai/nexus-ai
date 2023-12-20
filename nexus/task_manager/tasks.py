from nexus.task_manager.models import ContentBaseFileTaskManager
from nexus.task_manager.file_database.file_database import FileDataBase
from nexus.task_manager.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.usecases.content_base.content_base_dto import ContentBaseFileDTO

def add_file(task_manager: ContentBaseFileTaskManager, content_base_file_dto: ContentBaseFileDTO, file_database: FileDataBase):
    task_manager.update_status(ContentBaseFileTaskManager.STATUS_LOADING)
    response = file_database.add_file(content_base_file_dto.file)
    if response.status == 0:
        content_base_file_dto.file_url = response.url
        task_manager.content_base_file.file_url = content_base_file_dto.file_url
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
