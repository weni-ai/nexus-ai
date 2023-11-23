import boto3
import uuid

from django.conf import settings

from .file_uploader import FileUploader
from nexus.task_managers.models import UploadFileTaskManager

@dataclass
class file_response_dto:
    status: str,
    file_url: str

class S3FileUploader(FileUploader):

    def __init__(self, file):
        super().__init__(file)

    def upload_content_file(self) -> file_response_dto:
        s3_client = boto3.client(
            's3',
            # passar None
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        file_name = self.file.name + str(uuid.uuid4())
        response = {
            "status": UploadFileTaskManager.STATUS_SUCCESS
        }
        try:
            s3_client.upload_fileobj(self.file, settings.AWS_STORAGE_BUCKET_NAME, file_name)
            response.update({
                    "file_url": f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
                }
            )
        except Exception as exception:
            print(f"[S3 File Uploader] - {exception}")
            response["status"] = UploadFileTaskManager.STATUS_FAIL
        return response