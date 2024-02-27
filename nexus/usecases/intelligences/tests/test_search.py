from django.test import TestCase
from nexus.usecases.intelligences.search import IntelligenceGenerativeSearchUseCase
from .intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory
)
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.task_managers.file_database.wenigpt_database import WeniGPTDatabase
from typing import List


class SearchFileDatabase:
    status_code = 200

    def search_data(self, content_base_uuid: str, text: str):
        return {
            "status": 200,
            "data": {
                "response": ["Text1", "Text2", "Text3"]
            }
        }

class GenerativeAIDatabase:

    eng_answer = "ENGLISH ANSWER"
    spa_answer = "SPANISH ANSWER"
    por_answer = "PORTUGUESE ANSWER"

    answers = {
        "en": eng_answer,
        "pt": por_answer,
        "es": spa_answer
    }

    def request_wenigpt(
            self,
            contexts: List,
            question: str,
            language: str,
            content_base_uuid: str
        ):
        answer = self.answers.get(language)
        return {"answers": [answer], "id": "0"}


class IntelligenceGenerativeSearchUseCaseTestCase(TestCase):
    def setUp(self) -> None:
        self.usecase = IntelligenceGenerativeSearchUseCase(
            search_file_database=SearchFileDatabase(),
            generative_ai_database=GenerativeAIDatabase(),
        )
        self.content_base = ContentBaseFactory()

    def test_search_eng(self):

        content_base = self.content_base
        content_base.language = "en-us"
        content_base.save()

        response = self.usecase.search(
            content_base_uuid=str(self.content_base.uuid),
            text="text",
            language=content_base.language
        )
        self.assertEqual(
            GenerativeAIDatabase.eng_answer,
            response.get("answers")[0]
        )
    
    def test_search_spa(self):
        content_base = self.content_base
        content_base.language = "es"
        content_base.save()
        response = self.usecase.search(
            content_base_uuid=str(self.content_base.uuid),
            text="text",
            language=content_base.language
        )
        self.assertEqual(
            GenerativeAIDatabase.spa_answer,
            response.get("answers")[0]
        )
    
    def test_search_por(self):
        content_base = self.content_base
        content_base.language = "pt-br"
        content_base.save()
        response = self.usecase.search(
            content_base_uuid=str(self.content_base.uuid),
            text="text",
            language=content_base.language
        )
        self.assertEqual(
            GenerativeAIDatabase.por_answer,
            response.get("answers")[0]
        )
    
    def test_search_base(self):
        content_base = self.content_base
        content_base.language = "en"
        content_base.save()
        response = self.usecase.search(
            content_base_uuid=str(self.content_base.uuid),
            text="text",
            language="base"
        )
        self.assertEqual(
            GenerativeAIDatabase.answers.get(content_base.language),
            response.get("answers")[0]
        )
