from django.test import TestCase
from unittest.mock import patch

from ..wenigpt_database import get_prompt_by_language
from nexus.task_managers.tasks import create_wenigpt_logs

from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory
from nexus.usecases.intelligences.intelligences_dto import ContentBaseLogsDTO
from nexus.intelligences.models import ContentBaseLogs
from nexus.task_managers.file_database.wenigpt_database import WeniGPTDatabase


class Requests:
    def json(self):
        return {
            "output": {
                "text": "response"
            }
        }


class TestWenigptDB(TestCase):

    def setUp(self) -> None:
        self.context = "This is the context"
        self.question = "This is the question"
        self.content_base = ContentBaseFactory()

    def test_get_prompt_by_language(self):
        prompt = get_prompt_by_language('en', self.context, self.question)
        self.assertEqual(prompt, f'### Instruction:\nYou are a doctor treating a patient with amnesia. To answer the patient\'s questions, they will read a text beforehand to provide context. If you bring unknown information, outside of the text read, you may leave the patient confused. If the patient asks a question about information not present in the text, you need to respond politely that you do not have enough information to answer, because if you try to answer, you may bring information that will not help the patient recover their memory.\n\n### Input:\nTEXT: {self.context}\n\nQUESTION: {self.question}\nRemember, if it\'s not in the text, you need to respond politely that you do not have enough information to answer. We need to help the patient.\n\n### Response:\nANSWER:')
        prompt = get_prompt_by_language('es', self.context, self.question)
        self.assertEqual(prompt, f'### Instruction:\nUsted es un médico que trata a un paciente con amnesia. Para responder a las dudas del paciente, leerá un texto previamente para aportar contexto. Si trae información desconocida, fuera del texto leído, puede dejar al paciente confundido. Si el paciente hace una pregunta sobre información que no está presente en el texto, usted debe responder cortésmente que no tiene suficiente información para responder, porque si intenta responder, puede traer información que no ayudará al paciente a recuperar la memoria.\n\n### Input:\nTEXTO: {self.context}\n\nPREGUNTA: {self.question}\nRecuerde, si no está en el texto, usted debe responder cortésmente que no tiene suficiente información para responder. Necesitamos ayudar al paciente.\n\n### Response:\nRESPUESTA:')
        prompt = get_prompt_by_language('pt', self.context, self.question)
        self.assertEqual(prompt, f'''### Instruction:\nVocê é um médico tratando um paciente com amnésia. Para responder as perguntas do paciente, você irá ler um texto anteriormente para se contextualizar. Se você trouxer informações desconhecidas, fora do texto lido, poderá deixar o paciente confuso. Se o paciente fizer uma questão sobre informações não presentes no texto, você precisa responder de forma educada que você não tem informação suficiente para responder, pois se tentar responder, pode trazer informações que não ajudarão o paciente recuperar sua memória.\n\n### Input:\nTEXTO: {self.context}\n\nPERGUNTA: {self.question}\nLembre, se não estiver no texto, você precisa responder de forma educada que você não tem informação suficiente para responder. Precisamos ajudar o paciente.\n\n### Response:\nRESPOSTA:''')

    @patch("nexus.task_managers.tasks.trulens_evaluation")
    def test_create_wenigpt_logs(self, trulens_evaluation):
        trulens_evaluation.return_value = True
        log_dto = ContentBaseLogsDTO(
            content_base_uuid=str(self.content_base.uuid),
            question=self.question,
            language="pt",
            texts_chunks=["contexts"],
            full_prompt=["base_prompt"],
            weni_gpt_response="text_answers"
        )
        log = create_wenigpt_logs(log_dto.__dict__)
        self.assertIsInstance(log, ContentBaseLogs)

    @patch("nexus.task_managers.tasks.trulens_evaluation")
    @patch("requests.request")
    def test_request_wenigpt(self, requests, trulens_evaluation):
        trulens_evaluation.return_value = True
        requests.return_value = Requests()
        weni_db = WeniGPTDatabase()
        response = weni_db.request_wenigpt(
            contexts=[""],
            question=self.question,
            language="pt",
            content_base_uuid=str(self.content_base.uuid)
        )
        self.assertIsNotNone(response.get("question_uuid"))
