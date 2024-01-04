import boto3
import uuid
from django.conf import settings

from .file_database import FileDataBase, FileResponseDTO



class s3FileDatabase(FileDataBase):

    def add_file(self, file) -> FileResponseDTO:
        s3_client = boto3.client(
            's3',
            # aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            # aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        file_name = file.name + str(uuid.uuid4())
        response = FileResponseDTO()
        try:
            s3_client.upload_fileobj(file, settings.AWS_STORAGE_BUCKET_NAME, file_name)
            response.status = 0
            response.file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
        except Exception as exception:
            response.status = 1
            response.err = str(exception)
        return response
