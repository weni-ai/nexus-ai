from django.test import TestCase

from ..task_manager_dto import CeleryContentBaseFileTaskManagerDTO


class TestTaskManagerDTO(TestCase):

    def test_celery_content_base_file_task_manager_dto(self):
        dto = CeleryContentBaseFileTaskManagerDTO(
            status="status",
            uuid="uuid",
            created_by="created_by",
            content_base_file_uuid="content_base_file_uuid"
        )

        assert dto.status == "status"
        assert dto.uuid == "uuid"
        assert dto.created_by == "created_by"
        assert dto.content_base_file_uuid == "content_base_file_uuid"

        assert dto.to_json() == {
            "status": "status",
            "uuid": "uuid",
            "created_by": "created_by",
            "content_base_file_uuid": "content_base_file_uuid"
        }
