from nexus.usecases.orgs import get_org_by_content_base_uuid
from django.conf import settings
from nexus.task_managers.file_database import GPTDatabase
from nexus.task_managers.file_database.chatgpt import ChatGPTDatabase
from nexus.task_managers.file_database.wenigpt_database import WeniGPTDatabase


def get_gpt_by_content_base_uuid(content_base_uuid: str) -> GPTDatabase:
    org_uuid = str(get_org_by_content_base_uuid(content_base_uuid).uuid)
    if org_uuid in settings.CHATGPT_ORGS:
        api_key = settings.OPENAI_API_KEY

        if org_uuid == settings.IRC_UUID:
            api_key = settings.IRC_TOKEN

        return ChatGPTDatabase(api_key)

    return WeniGPTDatabase()
