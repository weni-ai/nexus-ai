import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from nexus.projects.consumers.project_consumer import ProjectConsumer
from nexus.projects.consumers.project_update_consumer import ProjectUpdateConsumer
from nexus.projects.models import Project
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.sync_vtex import (
    SyncProjectVtexUseCase,
    extract_vtex_fields,
    unwrap_eda_payload,
)
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class UnwrapAndExtractVtexFieldsTestCase(TestCase):
    def test_unwrap_flat_payload(self):
        body = {"uuid": "abc", "vtex_account": "store"}
        self.assertEqual(unwrap_eda_payload(body), body)

    def test_unwrap_amazonmq_envelope(self):
        inner = {"uuid": "abc", "vtex_account": "store"}
        body = {"event_type": "project.created", "producer": "EDA_PRODUCER", "data": inner}
        self.assertEqual(unwrap_eda_payload(body), inner)

    def test_extract_with_config(self):
        fields = extract_vtex_fields(
            {
                "vtex_account": "mystore",
                "config": {
                    "storefront_type": "vtex_io",
                    "vtex_host_store": "https://www.mystore.com.br",
                },
            }
        )
        self.assertEqual(fields.vtex_account, "mystore")
        self.assertEqual(fields.vtex_host_store, "https://www.mystore.com.br")
        self.assertEqual(fields.storefront_type, "vtex_io")
        self.assertTrue(fields.has_vtex_account)
        self.assertTrue(fields.has_vtex_host_store)
        self.assertTrue(fields.has_storefront_type)

    def test_extract_null_config(self):
        fields = extract_vtex_fields({"vtex_account": None, "config": None})
        self.assertIsNone(fields.vtex_account)
        self.assertTrue(fields.has_vtex_account)
        self.assertFalse(fields.has_vtex_host_store)
        self.assertFalse(fields.has_storefront_type)

    def test_extract_missing_vtex_fields(self):
        fields = extract_vtex_fields({"uuid": "abc", "config": {}})
        self.assertFalse(fields.has_vtex_account)
        self.assertFalse(fields.has_vtex_host_store)
        self.assertFalse(fields.has_storefront_type)


class SyncProjectVtexUseCaseTestCase(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.usecase = SyncProjectVtexUseCase()

    def test_create_mode_sets_filled_fields(self):
        fields = extract_vtex_fields(
            {
                "vtex_account": "mystore",
                "config": {
                    "vtex_host_store": "https://www.mystore.com.br",
                    "storefront_type": "vtex_io",
                },
            }
        )
        self.usecase.sync_project_vtex(str(self.project.uuid), fields, mode="create")
        self.project.refresh_from_db()
        self.assertEqual(self.project.vtex_account, "mystore")
        self.assertEqual(self.project.vtex_host_store, "https://www.mystore.com.br")
        self.assertEqual(self.project.storefront_type, "vtex_io")

    def test_create_mode_ignores_empty_fields(self):
        fields = extract_vtex_fields({"vtex_account": None, "config": {}})
        self.usecase.sync_project_vtex(str(self.project.uuid), fields, mode="create")
        self.project.refresh_from_db()
        self.assertIsNone(self.project.vtex_account)
        self.assertIsNone(self.project.vtex_host_store)

    def test_update_mode_applies_snapshot_including_null(self):
        self.project.vtex_account = "oldstore"
        self.project.vtex_host_store = "https://old.com"
        self.project.storefront_type = "legacy"
        self.project.save()

        fields = extract_vtex_fields(
            {
                "vtex_account": None,
                "config": {
                    "vtex_host_store": "https://www.mystore.com.br",
                    "storefront_type": "vtex_io",
                },
            }
        )
        self.usecase.sync_project_vtex(str(self.project.uuid), fields, mode="update")
        self.project.refresh_from_db()
        self.assertIsNone(self.project.vtex_account)
        self.assertEqual(self.project.vtex_host_store, "https://www.mystore.com.br")
        self.assertEqual(self.project.storefront_type, "vtex_io")

    def test_update_mode_link_account(self):
        fields = extract_vtex_fields({"vtex_account": "linked", "config": {}})
        self.usecase.sync_project_vtex(str(self.project.uuid), fields, mode="update")
        self.project.refresh_from_db()
        self.assertEqual(self.project.vtex_account, "linked")

    def test_project_not_found_returns_none(self):
        fields = extract_vtex_fields({"vtex_account": "x"})
        result = self.usecase.sync_project_vtex(str(uuid4()), fields, mode="update")
        self.assertIsNone(result)

    def test_unique_vtex_account_conflict_does_not_raise(self):
        other = ProjectFactory(vtex_account="taken")
        fields = extract_vtex_fields({"vtex_account": "taken", "config": {}})
        result = self.usecase.sync_project_vtex(str(self.project.uuid), fields, mode="update")
        self.assertEqual(result.uuid, self.project.uuid)
        self.project.refresh_from_db()
        # Conflicting value must not overwrite; other project keeps the account
        self.assertEqual(Project.objects.get(uuid=other.uuid).vtex_account, "taken")


class ProjectUpdateConsumerTestCase(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.consumer = ProjectUpdateConsumer()

    def _message(self, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.body = json.dumps(payload).encode()
        msg.delivery_tag = 42
        msg.channel = MagicMock()
        return msg

    def test_update_link_vtex_account(self):
        msg = self._message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "vtex_account": "mystore",
                "config": {},
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(42)
        self.project.refresh_from_db()
        self.assertEqual(self.project.vtex_account, "mystore")

    def test_update_host_store(self):
        msg = self._message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "vtex_account": "mystore",
                "config": {"vtex_host_store": "https://www.mystore.com.br"},
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(42)
        self.project.refresh_from_db()
        self.assertEqual(self.project.vtex_host_store, "https://www.mystore.com.br")

    def test_update_storefront_type(self):
        msg = self._message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "config": {"storefront_type": "vtex_io"},
            }
        )
        self.consumer.consume(msg)
        self.project.refresh_from_db()
        self.assertEqual(self.project.storefront_type, "vtex_io")

    def test_update_without_config_or_vtex_account(self):
        msg = self._message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "updated",
                "name": "only-name",
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(42)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.vtex_account)

    def test_ignores_non_updated_action(self):
        msg = self._message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "deleted",
                "vtex_account": "should-not-apply",
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(42)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.vtex_account)

    def test_ignores_project_type_update_action(self):
        msg = self._message(
            {
                "project_uuid": str(self.project.uuid),
                "action": "project_type_update",
                "vtex_account": "should-not-apply",
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(42)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.vtex_account)

    def test_missing_project_acks_and_skips(self):
        msg = self._message(
            {
                "project_uuid": str(uuid4()),
                "action": "updated",
                "vtex_account": "mystore",
                "config": {},
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(42)


class ProjectConsumerVtexTestCase(TestCase):
    def setUp(self):
        self.org = OrgFactory()
        self.user = self.org.created_by
        self.consumer = ProjectConsumer()

    def _message(self, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.body = json.dumps(payload).encode()
        msg.delivery_tag = 7
        msg.channel = MagicMock()
        return msg

    def _stub_create_project(self, mock_usecase):
        def create_project(project_dto, user_email):
            return ProjectFactory(
                uuid=project_dto.uuid,
                name=project_dto.name,
                org=self.org,
                created_by=self.user,
            )

        mock_usecase.return_value.create_project.side_effect = create_project

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_create_with_vtex_account(self, mock_usecase):
        self._stub_create_project(mock_usecase)
        project_uuid = str(uuid4())
        msg = self._message(
            {
                "uuid": project_uuid,
                "name": "commerce",
                "organization_uuid": str(self.org.uuid),
                "user_email": self.user.email,
                "is_template": False,
                "template_type_uuid": None,
                "brain_on": False,
                "authorizations": [],
                "vtex_account": "mystore",
                "config": {},
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(7)
        project = Project.objects.get(uuid=project_uuid)
        self.assertEqual(project.vtex_account, "mystore")

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_create_with_vtex_config(self, mock_usecase):
        self._stub_create_project(mock_usecase)
        project_uuid = str(uuid4())
        msg = self._message(
            {
                "uuid": project_uuid,
                "name": "commerce",
                "organization_uuid": str(self.org.uuid),
                "user_email": self.user.email,
                "is_template": False,
                "template_type_uuid": None,
                "brain_on": False,
                "authorizations": [],
                "vtex_account": "mystore",
                "config": {
                    "storefront_type": "vtex_io",
                    "vtex_host_store": "https://www.mystore.com.br",
                },
            }
        )
        self.consumer.consume(msg)
        project = Project.objects.get(uuid=project_uuid)
        self.assertEqual(project.vtex_host_store, "https://www.mystore.com.br")
        self.assertEqual(project.storefront_type, "vtex_io")

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_create_without_vtex_data(self, mock_usecase):
        self._stub_create_project(mock_usecase)
        project_uuid = str(uuid4())
        msg = self._message(
            {
                "uuid": project_uuid,
                "name": "non-vtex",
                "organization_uuid": str(self.org.uuid),
                "user_email": self.user.email,
                "is_template": False,
                "template_type_uuid": None,
                "brain_on": False,
                "authorizations": [],
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(7)
        project = Project.objects.get(uuid=project_uuid)
        self.assertIsNone(project.vtex_account)

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_create_envelope_amazonmq(self, mock_usecase):
        self._stub_create_project(mock_usecase)
        project_uuid = str(uuid4())
        msg = self._message(
            {
                "event_type": "project.created",
                "producer": "EDA_PRODUCER",
                "data": {
                    "uuid": project_uuid,
                    "name": "commerce",
                    "organization_uuid": str(self.org.uuid),
                    "user_email": self.user.email,
                    "is_template": False,
                    "template_type_uuid": None,
                    "brain_on": False,
                    "authorizations": [],
                    "vtex_account": "enveloped",
                    "config": {"storefront_type": "vtex_io"},
                },
            }
        )
        self.consumer.consume(msg)
        project = Project.objects.get(uuid=project_uuid)
        self.assertEqual(project.vtex_account, "enveloped")
        self.assertEqual(project.storefront_type, "vtex_io")

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_create_reprocess_is_idempotent(self, mock_usecase):
        from django.db import IntegrityError

        project = ProjectFactory(org=self.org, created_by=self.user, name="existing")
        mock_usecase.return_value.create_project.side_effect = IntegrityError("duplicate")
        msg = self._message(
            {
                "uuid": str(project.uuid),
                "name": project.name,
                "organization_uuid": str(self.org.uuid),
                "user_email": self.user.email,
                "is_template": False,
                "template_type_uuid": None,
                "brain_on": False,
                "authorizations": [],
                "vtex_account": "reprocessed",
                "config": {"vtex_host_store": "https://www.reprocessed.com"},
            }
        )
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(7)
        self.assertEqual(Project.objects.filter(uuid=project.uuid).count(), 1)
        project.refresh_from_db()
        self.assertEqual(project.vtex_account, "reprocessed")
        self.assertEqual(project.vtex_host_store, "https://www.reprocessed.com")
