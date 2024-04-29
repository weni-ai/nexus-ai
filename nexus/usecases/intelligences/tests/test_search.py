from django.test import TestCase
from nexus.usecases.intelligences.search import IntelligenceGenerativeSearchUseCase
from .intelligence_factory import (
    ContentBaseFactory,
)

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


class MockGenerativeAIDatabase:

    eng_answer = "ENGLISH ANSWER"
    spa_answer = "SPANISH ANSWER"
    por_answer = "PORTUGUESE ANSWER"

    answers = {
        "en": eng_answer,
        "pt": por_answer,
        "es": spa_answer
    }

    def request_gpt(
            self,
            contexts: List,
            question: str,
            language: str,
            content_base_uuid: str,
            testing: bool = True,
    ):
        answer = self.answers.get(language)
        return {"answers": [answer], "id": "0"}


class IntelligenceGenerativeSearchUseCaseTestCase(TestCase):
    def setUp(self) -> None:
        self.usecase = IntelligenceGenerativeSearchUseCase(
            search_file_database=SearchFileDatabase(),
            generative_ai_database=MockGenerativeAIDatabase(),
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
            MockGenerativeAIDatabase.eng_answer,
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
            MockGenerativeAIDatabase.spa_answer,
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
            MockGenerativeAIDatabase.por_answer,
            response.get("answers")[0]
        )

    def test_search_base(self):
        content_base = self.content_base
        content_base.language = "en-us"
        content_base.save()
        print("Content base language: ", content_base.language)
        response = self.usecase.search(
            content_base_uuid=str(content_base.uuid),
            text="text",
            language="base"
        )
        print("Response answer: ", response.get("answers")[0])
        self.assertEqual(
            MockGenerativeAIDatabase.answers.get("en"),
            response.get("answers")[0]
        )
