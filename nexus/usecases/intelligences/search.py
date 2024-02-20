
from django.conf import settings
from nexus.evaluation import f_qa_relevance, f_groundedness, f_qs_relevance
from nexus.usecases.trulens import WeniGPTWrapper

from trulens_eval import TruCustomApp


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
        language = self._language_code(language.lower())
        wenigpt = WeniGPTWrapper(content_base_uuid, language)
        tru_recorder = TruCustomApp(wenigpt, 
            app_id=f"WeniGPT v{settings.WENIGPT_VERSION}",
            feedbacks=[f_qa_relevance, f_qs_relevance, f_groundedness]
        )
        with tru_recorder as recording:
            response = wenigpt.respond_to_query(text)
            return response
