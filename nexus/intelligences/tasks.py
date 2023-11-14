import pendulum

from nexus.celery import app
from nexus.task_managers.models import ContentBaseFileUpload
from nexus.usecases.file_hub.s3_file_uploader import S3FileUploader, FileUploader


@app.task("upload_file")
def upload_file(task_uuid, uploader: FileUploader):
    task = ContentBaseFileUpload.objects.get(uuid=task_uuid)
    task.status = ContentBaseFileUpload.STATUS_UPLOADING
    task.save(update_fields=["status"])
    response = uploader.upload_content_file()
    task.status = response.get("status")
    task.file_path = response.get("file_path")
    task.end_at = pendulum.now()
    task.save(update_fields=["status, file_path", "end_at"])