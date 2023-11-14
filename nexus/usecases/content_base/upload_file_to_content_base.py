from nexus.intelligences.models import ContentBaseFile
from nexus.task_managers.models import UploadFileTaskManager
from nexus.users.models import User
from nexus.usecases.file_hub.s3_file_uploader import FileUploader, S3FileUploader
from nexus.intelligences.tasks import upload_file

from .get_content_base_by_uuid import get_content_base_by_uuid


def upload_file_content_base(file, content_base_uuid: str, extension_file: str, user: User, uploader: FileUploader):
    content_base = get_content_base_by_uuid(content_base_uuid=content_base_uuid)

    content_base_file = ContentBaseFile.objects.create(
        extension_file=extension_file,
        content_base=content_base,
        created_by=user
    )

    task = UploadFileTaskManager.objects.create(
        uploaded_by=user,
        content_base=content_base_file
    )

    upload_file.apply_async(args=[task.uuid, uploader])