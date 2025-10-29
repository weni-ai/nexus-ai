# Mock repositories for unit tests and local development

from router.repositories import Repository
from router.repositories.entities import ResolutionEntities


class MockRepository(Repository):
    def storage_message(
        self,
        project_uuid: str,
        contact_urn: str,
        message_data: dict,
        channel_uuid: str = None,
        resolution_status: int = ResolutionEntities.IN_PROGRESS,
        ttl_hours: int = 48,
    ) -> None:
        pass

    def get_messages(
        self, project_uuid: str, contact_urn: str, channel_uuid: str, limit: int = 50, cursor: str = None
    ) -> dict:
        return {"items": [], "next_cursor": None, "total_count": 0}

    def get_messages_for_conversation(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        start_date: str,
        end_date: str,
        resolution_status: int = ResolutionEntities.IN_PROGRESS,
    ) -> list:
        return []

    def _format_message(self, item: dict) -> dict:
        return {
            "text": item["message_text"],
            "source": item["source_type"],
            "created_at": item["created_at"],
        }

    def delete_messages(self, project_uuid: str, contact_urn: str, channel_uuid: str = None) -> None:
        return None

    def add_message(self, project_uuid: str, contact_urn: str, message: dict, channel_uuid: str = None) -> None:
        return None

    def store_batch_messages(
        self, project_uuid: str, contact_urn: str, messages: list, key: str, channel_uuid: str = None
    ) -> None:
        return None
