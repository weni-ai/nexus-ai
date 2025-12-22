import os

import django
from django.test import TestCase

from nexus.logs.models import MessageLog
from nexus.usecases.logs.create import CreateLogUsecase
from nexus.usecases.logs.tests.logs_factory import MessageLogFactory
from router.entities import ContactMessageDTO
from router.repositories import orm

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

django.setup()


class TestFlowsORMRepository(TestCase):
    def setUp(self) -> None:
        self.msg_log: MessageLog = MessageLogFactory()
        self.repository = orm.MessageLogsRepository()

    def test_list_cached_messages(self):
        project_uuid = self.msg_log.project.uuid
        contact_urn = self.msg_log.message.contact_urn

        create_usecase = CreateLogUsecase()
        create_usecase._create_redis_cache(self.msg_log, project_uuid)

        cache_data: list = self.repository.list_cached_messages(project_uuid, contact_urn)
        msg_data: ContactMessageDTO = cache_data[0]

        self.assertEqual(msg_data.text, self.msg_log.message.text)
