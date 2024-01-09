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

        name, extension = file.name.split(".")
        file_name = f"{name}-{uuid.uuid4()}.{extension}"
        response = FileResponseDTO(err="", file_url="", status=1)
        try:
            print(f"[ S3FileDatabase ] - uploading {file_name}")
            s3_client.upload_fileobj(file, settings.AWS_S3_BUCKET_NAME, file_name)
            response.status = 0
            response.file_url = f"https://{settings.AWS_S3_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
        except Exception as exception:
            response.status = 1
            response.err = str(exception)
        print(f"[ S3FileDatabase ] - uploaded {file_name}")
        return response
