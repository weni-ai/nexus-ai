from typing import List

from django.conf import settings

from nexus.intelligences.llms import WeniGPTClient
from nexus.task_managers.file_database import GPTDatabase
from nexus.usecases.intelligences.intelligences_dto import ContentBaseLogsDTO
from router.entities.intelligences import LLMSetupDTO


class WeniGPTDatabase(GPTDatabase):
    language_codes = {
        "pt": "português",
        "en": "inglês",
        "es": "espanhol",
    }

    def __init__(self):
        self.url = settings.WENIGPT_API_URL
        self.token = settings.WENIGPT_API_TOKEN
        self.cookie = settings.WENIGPT_COOKIE
        self.default_instructions = settings.DEFAULT_INSTRUCTIONS
        self.default_agent = dict(
            name=settings.DEFAULT_AGENT_NAME,
            role=settings.DEFAULT_AGENT_ROLE,
            goal=settings.DEFAULT_AGENT_GOAL,
            personality=settings.DEFAULT_AGENT_PERSONALITY,
        )
        self.default_llm_config = LLMSetupDTO(
            model="wenigpt",
            model_version=settings.WENIGPT_DEFAULT_VERSION,
            temperature=settings.WENIGPT_TEMPERATURE,
            top_p=settings.WENIGPT_TOP_P,
            top_k=settings.WENIGPT_TOP_K,
        )
        self.default_wenigpt_client = WeniGPTClient(settings.WENIGPT_DEFAULT_VERSION)

    def request_gpt(self, contexts: List, question: str, language: str, content_base_uuid: str, testing: bool = False):
        from nexus.task_managers.tasks import create_wenigpt_logs

        gpt_response = self.default_wenigpt_client.request_gpt(
            self.default_instructions, contexts, self.default_agent, question, self.default_llm_config
        )

        text_answer = None
        try:
            text_answer = gpt_response.get("answers")[0].get("text")
            log_dto = ContentBaseLogsDTO(
                content_base_uuid=content_base_uuid,
                question=question,
                language=language,
                texts_chunks=contexts,
                full_prompt="",
                weni_gpt_response=text_answer,
                testing=testing,
            )
            log = create_wenigpt_logs(log_dto.__dict__)
            return {"answers": [{"text": text_answer}], "id": "0", "question_uuid": str(log.user_question.uuid)}
        except Exception as e:
            response = {"error": str(e)}
            import logging

            logger = logging.getLogger(__name__)
            logger.error("wenigpt_database error: %s", response)

        return {"answers": None, "id": "0", "message": "No context found for this question"}
