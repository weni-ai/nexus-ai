from nexus.usecases.logs.tests.logs_factory import MessageLogFactory
from nexus.usecases.logs.create import CreateLogUsecase
from nexus.logs.models import MessageLog

from django.test import TestCase
from django.core.cache import cache


class TestCreateLogUsecase(TestCase):

    def setUp(self) -> None:
        self.msg_log: MessageLog = MessageLogFactory()

        self.msg_log1: MessageLog = MessageLogFactory()
        self.msg_log2: MessageLog = MessageLogFactory()
        self.project_uuid1 = self.msg_log1.project.uuid
        self.project_uuid2 = self.msg_log2.project.uuid

    def test_redis_cache(self):
        project_uuid = self.msg_log.project.uuid

        usecase = CreateLogUsecase()
        usecase._create_redis_cache(self.msg_log, project_uuid)

        cache_key = f"last_5_messages_{project_uuid}_{self.msg_log.message.contact_urn}"
        cache_data = cache.get(cache_key)
        cache_data = cache_data[0]

        self.assertEqual(cache_data['text'], self.msg_log.message.text)

    def test_redis_cache_multiple_conversations(self):
        usecase = CreateLogUsecase()

        for i in range(6):
            msg_log = MessageLogFactory(
                project=self.msg_log1.project,
                message__contact_urn=self.msg_log1.message.contact_urn,
                message__text=f'Text {i}'
            )
            usecase._create_redis_cache(msg_log, self.project_uuid1)

        for i in range(6):
            msg_log = MessageLogFactory(
                project=self.msg_log2.project,
                message__contact_urn=self.msg_log2.message.contact_urn,
                message__text=f'Text {i}'
            )
            usecase._create_redis_cache(msg_log, self.project_uuid2)

        cache_key1 = f"last_5_messages_{self.project_uuid1}_{self.msg_log1.message.contact_urn}"
        cache_data1 = cache.get(cache_key1)
        self.assertEqual(len(cache_data1), 5)
        self.assertEqual(cache_data1[0]['text'], 'Text 5')

        cache_key2 = f"last_5_messages_{self.project_uuid2}_{self.msg_log2.message.contact_urn}"
        cache_data2 = cache.get(cache_key2)
        self.assertEqual(len(cache_data2), 5)
        self.assertEqual(cache_data2[0]['text'], 'Text 5')

        self.assertNotEqual(cache_data1, cache_data2)
