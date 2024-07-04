import uuid
import boto3
from os.path import basename
from django.conf import settings

from .file_database import FileDataBase, FileResponseDTO


class s3FileDatabase(FileDataBase):
    def __init__(self) -> None:
        self.s3_client = boto3.client(
            's3',
            # aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            # aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

    def add_file(self, file) -> FileResponseDTO:
        file_name = basename(file.name)
        name, extension = file_name.rsplit(".", 1)
        name = name.replace(".", "_")
        file_name = f"{name}-{uuid.uuid4()}.{extension}"
        response = FileResponseDTO()
        try:
            self.s3_client.upload_fileobj(file, settings.AWS_S3_BUCKET_NAME, file_name)
            response.status = 0
            response.file_url = f"https://{settings.AWS_S3_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
            response.file_name = file_name
        except Exception as exception:
            response.status = 1
            response.err = str(exception)
        return response

    def create_presigned_url(self, file_name: str, expiration: int = 3600) -> str:
        return self.s3_client.generate_presigned_url('get_object', Params={'Bucket': settings.AWS_S3_BUCKET_NAME, 'Key': file_name}, ExpiresIn=expiration)
