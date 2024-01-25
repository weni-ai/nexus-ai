from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.task_managers.file_database.wenigpt_database import WeniGPTDatabase


class IntelligenceGenerativeSearchUseCase():

    def language_code(self, language: str):
        languages = {
            "por": "pt",
            "pt": "pt",
            "pt-br": "pt",
            "base": "pt",
            "en": "en",
            "en-us": "en",
            "es": "es",
            "es-es": "es",
        }
        return languages.get(language, "pt")

    def search(self, content_base_uuid: str, text: str, language: str):
        language = self.language_code(language.lower())
        response = SentenXFileDataBase().search_data(content_base_uuid, text)
        if response.get("status") != 200:
            raise Exception(response.get("data"))
        wenigpt_database = WeniGPTDatabase()
        return wenigpt_database.request_wenigpt(contexts=response.get("data", []).get("response"), question=text, language=language)
