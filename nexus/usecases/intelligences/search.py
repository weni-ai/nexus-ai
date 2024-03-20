from nexus.intelligences.models import ContentBase


class IntelligenceGenerativeSearchUseCase():
    def __init__(self, search_file_database, generative_ai_database) -> None:
        self.search_file_database = search_file_database
        self.generative_ai_database = generative_ai_database

    def _language_code(self, language: str, content_base_uuid: str = None) -> str:
        if language == "base":
            return ContentBase.objects.get(uuid=content_base_uuid).language

        codes = {
            "por": "pt",
            "pt-br": "pt",
            "eng": "en",
            "en-us": "en",
            "spa": "es",
            "es": "es"

        }
        return codes.get(language, "pt")

    def search(self, content_base_uuid: str, text: str, language: str):
        response = self.search_file_database.search_data(content_base_uuid, text)

        if response.get("status") != 200:
            raise Exception(response.get("data"))

        language = self._language_code(language.lower(), content_base_uuid)

        return self.generative_ai_database.request_gpt(
            contexts=response.get("data", []).get("response"),
            question=text,
            language=language,
            content_base_uuid=content_base_uuid,
        )
