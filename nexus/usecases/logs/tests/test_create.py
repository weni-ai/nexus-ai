from django.test import TestCase

from nexus.zeroshot.models import ZeroshotLogs
from nexus.usecases.logs.create import CreateZeroshotLogsUseCase
from nexus.usecases.logs.entities import ZeroshotDTO


class CreateZeroshotLogsTestCase(TestCase):
    def test_create_log(self):

        text = 'oi'
        classification = "None"
        other = True
        options = [
            {'id': 1, 'class': 'Lorem Ipsum', 'context': 'Dolor sit Amet'},
            {'id': 2, 'class': 'consectetur adipiscing elit', 'context': 'Vestibulum pharetra erat et nisl pretium viverra'}
        ]
        nlp_log = '{"output": {"other": true, "classification": "None"}}'
        language = 'por'

        dto = ZeroshotDTO(
            text=text,
            classification=classification,
            other=other, options=options,
            nlp_log=nlp_log,
            language=language
        )
        log = CreateZeroshotLogsUseCase(dto).create()

        self.assertIsInstance(log, ZeroshotLogs)
