import logging
import uuid

import boto3
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

logger = logging.getLogger(__name__)


def validate_mime_type(content_type: str) -> bool:
    image = ["image/png", "image/jpeg", "image/gif", "image/webp"]
    video = ["video/mp4", "video/x-msvideo"]
    audio = ["audio/mpeg", "audio/wav", "audio/ogg"]
    doc = [
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/pdf",
        "text/plain",
    ]
    mime = image + audio + video + doc

    return content_type in mime


class AttachmentPreviewStorage(S3Boto3Storage):
    location = "media/preview/attachments/"
    file_overwrite = False
    custom_domain = False
    override_available_name = True

    def get_available_name(self, name, max_length=None):
        if self.override_available_name:
            ext = name.split(".")[-1]
            filename = f"av_{uuid.uuid4()}.{ext}"
            return super().get_available_name(filename, max_length)
        return super().get_available_name(name, max_length)


class AgentSystemLogoStorage(S3Boto3Storage):
    location = ""
    file_overwrite = False
    custom_domain = False


class DeleteStorageFile:
    def __init__(self):
        self.s3_client = boto3.client("s3", region_name=settings.AWS_S3_REGION_NAME)

    def delete_file(self, file_name):
        try:
            response = self.s3_client.delete_object(
                Bucket=settings.AWS_S3_BUCKET_NAME, Key=f"{AttachmentPreviewStorage.location}/{file_name}"
            )
            return response
        except Exception as e:
            logger.error("Error deleting file", extra={"file_name": file_name, "error": str(e)})
            return None
