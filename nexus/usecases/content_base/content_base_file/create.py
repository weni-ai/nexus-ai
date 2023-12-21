from dataclasses import dataclass

from nexus.usecases.content_base.content_base_dto import ContentBaseFileDTO
from nexus.usecases.content_base import get_by_uuid as content_base_usecase
from nexus.intelligences.models import ContentBaseFile
from nexus.usecases import orgs, users


class CreateContentBaseFileUseCase():
    
    def create_content_base_file(self, content_base_file: ContentBaseFileDTO) -> ContentBaseFile:
        user = users.get_by_email(content_base_file.user_email)
        content_base = content_base_usecase.get_by_uuid(content_base_uuid=content_base_file.content_base_uuid)
        content_base_file = ContentBaseFile.objects.create(
            file=content_base_file.file_url,
            extension_file=content_base_file.extension_file,
            content_base=content_base,
            created_by=user
        )
        return content_base_file
