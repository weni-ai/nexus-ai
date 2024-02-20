from django.conf import settings

from nexus.task_managers.file_database.wenigpt_database import WeniGPTDatabase
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from trulens_eval.tru_custom_app import instrument
from trulens_eval import Tru


class WeniGPTWrapper:
    def __init__(self, content_base_uuid: str = None, language: str = None) -> None:
        self.sentenx = SentenXFileDataBase()
        self.wenigpt = WeniGPTDatabase()
        self.content_base_uuid = content_base_uuid
        self.language = language
        self.tru = Tru(
            database_url=settings.TRULENS_DATABASE_URL,
            database_redact_keys=True
        )

    @instrument
    def retrive_chunks(self, text):
        response = self.sentenx.search_data(self.content_base_uuid, text)
        chunks = response.get("data", []).get("response")
        return chunks

    @instrument
    def respond_to_query(self, input):
        chunks = self.retrive_chunks(input)
        response = self.wenigpt.request_wenigpt(
            contexts=chunks,
            question=input,
            language=self.language,
            content_base_uuid=self.content_base_uuid,
        )
        return response
