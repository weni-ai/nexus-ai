from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.task_managers.file_database.wenigpt_database import WeniGPTDatabase


class IntelligenceGenerativeSearchUseCase():
    def _language_code(self, language):
        codes = {
            "por": "pt",
            "pt-br": "pt",
            "base": "pt",
            "eng": "en",
            "en-us": "en",
            "spa": "es",
            "es": "es"

        }
        return codes.get(language, "pt")

    def search(self, content_base_uuid: str, text: str, language: str):
        response = SentenXFileDataBase().search_data(content_base_uuid, text)
        if response.get("status") != 200:
            raise Exception(response.get("data"))
        wenigpt_database = WeniGPTDatabase()
        language = self._language_code(language.lower())
        return wenigpt_database.request_wenigpt(
            contexts=response.get("data", []).get("response"),
            question=text,
            language=language
        )
