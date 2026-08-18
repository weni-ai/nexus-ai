from unittest.mock import patch

from django.test import TestCase

from nexus.intelligences.models import ContentBaseText
from nexus.logs.models import RecentActivities
from nexus.task_managers.models import (
    ContentBaseLinkTaskManager,
    ContentBaseTextTaskManager,
    TaskManager,
)
from nexus.usecases.intelligences.delete import DeleteContentBaseTextUseCase
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    ContentBaseFileFactory,
    ContentBaseLinkFactory,
    ContentBaseTextFactory,
    IntegratedIntelligenceFactory,
)
from nexus.usecases.intelligences.tests.mocks import MockFileDataBase
from nexus.usecases.task_managers.celery_task_manager import (
    CeleryTaskManagerUseCase,
    publish_ingest_success_create,
)
from nexus.usecases.task_managers.tests.task_manager_factory import ContentBaseFileTaskManagerFactory


class IngestSuccessCreateActivityTestCase(TestCase):
    def setUp(self) -> None:
        self.integrated = IntegratedIntelligenceFactory()
        self.project = self.integrated.project
        self.user = self.project.created_by
        self.content_base = self.integrated.intelligence.contentbases.filter(is_router=True).first()
        if self.content_base is None:
            self.content_base = ContentBaseFactory(
                intelligence=self.integrated.intelligence,
                created_by=self.user,
                is_router=True,
            )

    @patch("nexus.usecases.task_managers.celery_task_manager.event_manager.notify")
    def test_file_success_notifies_create(self, mock_notify):
        content_base_file = ContentBaseFileFactory(content_base=self.content_base, created_by=self.user)
        task = ContentBaseFileTaskManagerFactory(
            content_base_file=content_base_file,
            created_by=self.user,
            status=TaskManager.STATUS_PROCESSING,
        )

        publish_ingest_success_create(task)

        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        self.assertEqual(kwargs["event"], "contentbase_file_activity")
        self.assertEqual(kwargs["action_type"], "C")
        self.assertEqual(kwargs["content_base_file"], content_base_file)

    @patch("nexus.usecases.task_managers.celery_task_manager.event_manager.notify")
    def test_link_success_notifies_create(self, mock_notify):
        content_base_link = ContentBaseLinkFactory(content_base=self.content_base, created_by=self.user)
        task = ContentBaseLinkTaskManager.objects.create(
            status=TaskManager.STATUS_PROCESSING,
            created_by=self.user,
            content_base_link=content_base_link,
        )

        publish_ingest_success_create(task)

        kwargs = mock_notify.call_args.kwargs
        self.assertEqual(kwargs["event"], "contentbase_link_activity")
        self.assertEqual(kwargs["action_type"], "C")
        self.assertEqual(kwargs["content_base_link"], content_base_link)

    @patch("nexus.usecases.task_managers.celery_task_manager.event_manager.notify")
    def test_text_success_does_not_notify_create(self, mock_notify):
        content_base_text = ContentBaseTextFactory(content_base=self.content_base, created_by=self.user)
        task = ContentBaseTextTaskManager.objects.create(
            status=TaskManager.STATUS_PROCESSING,
            created_by=self.user,
            content_base_text=content_base_text,
            file_url="http://test.com/t.txt",
            file_name="t.txt",
        )

        publish_ingest_success_create(task)

        mock_notify.assert_not_called()

    @patch("nexus.usecases.task_managers.celery_task_manager.event_manager.notify")
    def test_skips_create_when_content_already_succeeded(self, mock_notify):
        content_base_file = ContentBaseFileFactory(content_base=self.content_base, created_by=self.user)
        ContentBaseFileTaskManagerFactory(
            content_base_file=content_base_file,
            created_by=self.user,
            status=TaskManager.STATUS_SUCCESS,
        )
        retry_task = ContentBaseFileTaskManagerFactory(
            content_base_file=content_base_file,
            created_by=self.user,
            status=TaskManager.STATUS_PROCESSING,
        )

        publish_ingest_success_create(retry_task)

        mock_notify.assert_not_called()

    @patch("nexus.usecases.task_managers.celery_task_manager.event_manager.notify")
    def test_update_task_status_to_success_publishes_once(self, mock_notify):
        content_base_file = ContentBaseFileFactory(content_base=self.content_base, created_by=self.user)
        task = ContentBaseFileTaskManagerFactory(
            content_base_file=content_base_file,
            created_by=self.user,
            status=TaskManager.STATUS_PROCESSING,
        )

        CeleryTaskManagerUseCase().update_task_status(str(task.uuid), TaskManager.STATUS_SUCCESS, "file")
        CeleryTaskManagerUseCase().update_task_status(str(task.uuid), TaskManager.STATUS_SUCCESS, "file")

        self.assertEqual(mock_notify.call_count, 1)

    @patch("nexus.usecases.task_managers.celery_task_manager.event_manager.notify")
    def test_fail_status_does_not_publish(self, mock_notify):
        content_base_file = ContentBaseFileFactory(content_base=self.content_base, created_by=self.user)
        task = ContentBaseFileTaskManagerFactory(
            content_base_file=content_base_file,
            created_by=self.user,
            status=TaskManager.STATUS_PROCESSING,
        )

        CeleryTaskManagerUseCase().update_task_status(str(task.uuid), TaskManager.STATUS_FAIL, "file")

        mock_notify.assert_not_called()


class ContentBaseTextDeleteActivityTestCase(TestCase):
    def setUp(self) -> None:
        self.integrated = IntegratedIntelligenceFactory()
        self.user = self.integrated.created_by
        self.content_base = self.integrated.intelligence.contentbases.filter(is_router=True).first()
        if self.content_base is None:
            self.content_base = ContentBaseFactory(
                intelligence=self.integrated.intelligence,
                created_by=self.user,
                is_router=True,
            )
        self.contentbasetext = ContentBaseTextFactory(content_base=self.content_base, created_by=self.user)

    def test_delete_emits_delete_activity(self):
        notify_calls = []

        def _capture(**kwargs):
            notify_calls.append(kwargs)

        use_case = DeleteContentBaseTextUseCase(
            file_database=MockFileDataBase(),
            event_manager_notify=_capture,
        )
        use_case.delete_contentbasetext(
            contentbasetext_uuid=str(self.contentbasetext.uuid),
            user_email=self.user.email,
        )

        self.assertEqual(ContentBaseText.objects.count(), 0)
        self.assertEqual(len(notify_calls), 1)
        self.assertEqual(notify_calls[0]["event"], "contentbase_text_activity")
        self.assertEqual(notify_calls[0]["action_type"], "D")

    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_delete_creates_recent_activity_row(self, mock_amq):
        use_case = DeleteContentBaseTextUseCase(file_database=MockFileDataBase())
        use_case.delete_contentbasetext(
            contentbasetext_uuid=str(self.contentbasetext.uuid),
            user_email=self.user.email,
        )

        activity = RecentActivities.objects.get()
        self.assertEqual(activity.action_type, "D")
        self.assertEqual(activity.action_model, "ContentBaseText")
        mock_amq.assert_called_once()
