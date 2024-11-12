from nexus.usecases.logs.tests.logs_factory import MessageLogFactory
from nexus.usecases.logs.create import CreateLogUsecase
from nexus.logs.models import MessageLog

from django.test import TestCase
from django.core.cache import cache


class TestCreateLogUsecase(TestCase):

    def setUp(self) -> None:
        self.msg_log: MessageLog = MessageLogFactory()

    def test_redis_cache(self):
        project_uuid = self.msg_log.project.uuid

        usecase = CreateLogUsecase()
        usecase._create_redis_cache(self.msg_log, project_uuid)

        cache_key = f"last_5_messages_{project_uuid}_{self.msg_log.message.contact_urn}"
        cache_data = cache.get(cache_key)
        cache_data = cache_data[0]

        self.assertEqual(cache_data['text'], self.msg_log.message.text)
