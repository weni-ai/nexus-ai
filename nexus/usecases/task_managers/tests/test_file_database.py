from django.test import TestCase

from nexus.task_managers.file_database.chatgpt import ChatGPTDatabase
from nexus.task_managers.file_database.wenigpt_database import WeniGPTDatabase
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory
from nexus.usecases.orgs import get_org_by_content_base_uuid
from nexus.usecases.task_managers.file_database import get_gpt_by_content_base_uuid


class TestGPTDB(TestCase):
    def setUp(self) -> None:
        self.contentbase_chatgpt = ContentBaseFactory()
        self.contentbase_wenigpt = ContentBaseFactory()

    def test_get_chatgpt_db(self):
        gpt = get_gpt_by_content_base_uuid(str(self.contentbase_chatgpt.uuid))
        self.assertIsInstance(gpt, WeniGPTDatabase)

    def test_get_wenigpt_db(self):
        wenigpt_cb = self.contentbase_wenigpt
        org_uuid = str(get_org_by_content_base_uuid(str(wenigpt_cb.uuid)).uuid)

        with self.settings(CHATGPT_ORGS=[org_uuid]):
            gpt = get_gpt_by_content_base_uuid(str(wenigpt_cb.uuid))
            self.assertIsInstance(gpt, ChatGPTDatabase)
