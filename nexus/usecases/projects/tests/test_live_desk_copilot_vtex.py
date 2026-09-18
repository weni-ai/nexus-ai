import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase, TestCase

from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify
from nexus.projects.consumers.project_consumer import WeniEDAProjectConsumer
from nexus.projects.consumers.project_update_consumer import ProjectUpdateConsumer
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.live_desk_copilot import (
    assign_parent_project,
    extract_parent_uuid,
    vtex_runtime_fields,
)
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.projects.sync_live_desk_copilot import SyncLiveDeskCopilotUseCase
from nexus.usecases.projects.sync_vtex import SyncProjectVtexUseCase, extract_vtex_fields
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from router.services.pre_generation_service import PreGenerationService


class ExtractParentUuidTestCase(SimpleTestCase):
    def test_parent_uuid_key(self):
        self.assertEqual(extract_parent_uuid({"parent_uuid": "abc"}), ("abc", True))

    def test_parent_project_uuid_alias(self):
        self.assertEqual(extract_parent_uuid({"parent_project_uuid": "abc"}), ("abc", True))

    def test_main_project_uuid_alias(self):
        self.assertEqual(extract_parent_uuid({"main_project_uuid": "abc"}), ("abc", True))

    def test_explicit_null_clears(self):
        self.assertEqual(extract_parent_uuid({"parent_uuid": None}), (None, True))

    def test_missing_key(self):
        self.assertEqual(extract_parent_uuid({"uuid": "p1"}), (None, False))


class VtexRuntimeFieldsTestCase(TestCase):
    def test_normal_project_uses_own_account(self):
        project = ProjectFactory(
            vtex_account="ownstore",
            vtex_host_store="https://own.example",
            storefront_type="vtex_io",
        )
        self.assertEqual(vtex_runtime_fields(project)["vtex_account"], "ownstore")
        self.assertEqual(vtex_runtime_fields(project)["vtex_host_store"], "https://own.example")
        self.assertEqual(vtex_runtime_fields(project)["storefront_type"], "vtex_io")

    def test_copilot_uses_parent_account(self):
        parent = ProjectFactory(
            vtex_account="mainstore",
            vtex_host_store="https://main.example",
            storefront_type="vtex_io",
        )
        copilot = ProjectFactory(
            is_live_desk_copilot=True,
            parent_project=parent,
            vtex_account=None,
        )
        fields = vtex_runtime_fields(copilot)
        self.assertEqual(fields["vtex_account"], "mainstore")
        self.assertEqual(fields["vtex_host_store"], "https://main.example")
        self.assertEqual(fields["storefront_type"], "vtex_io")

    def test_copilot_without_parent_falls_back_to_own_fields(self):
        copilot = ProjectFactory(is_live_desk_copilot=True, vtex_account=None)
        self.assertIsNone(vtex_runtime_fields(copilot)["vtex_account"])

    def test_assign_parent_ignores_self(self):
        project = ProjectFactory()
        self.assertFalse(assign_parent_project(project, str(project.uuid)))
        self.assertIsNone(project.parent_project_id)

    def test_assign_parent_missing_project_does_not_raise(self):
        project = ProjectFactory()
        self.assertFalse(assign_parent_project(project, str(uuid4())))
        self.assertIsNone(project.parent_project_id)


class CreateProjectParentTestCase(TestCase):
    def test_create_project_persists_parent(self):
        org = OrgFactory()
        parent = ProjectFactory(org=org, created_by=org.created_by)
        project_dto = ProjectCreationDTO(
            uuid=uuid4().hex,
            name="copilot",
            org_uuid=org.uuid,
            is_template=False,
            template_type_uuid=None,
            brain_on=False,
            authorizations=[],
            is_live_desk_copilot=True,
            parent_uuid=str(parent.uuid),
        )
        project = ProjectsUseCase(event_manager_notify=mock_event_manager_notify).create_project(
            project_dto=project_dto, user_email=org.created_by.email
        )
        self.assertTrue(project.is_live_desk_copilot)
        self.assertEqual(project.parent_project_id, parent.uuid)


class SyncLiveDeskCopilotUseCaseTestCase(TestCase):
    def setUp(self):
        self.parent = ProjectFactory()
        self.project = ProjectFactory()
        self.usecase = SyncLiveDeskCopilotUseCase()
        self.notify_patcher = patch("nexus.usecases.projects.sync_live_desk_copilot.notify_async")
        self.mock_notify = self.notify_patcher.start()
        self.addCleanup(self.notify_patcher.stop)

    def test_update_sets_flag_and_parent(self):
        self.usecase.sync(
            str(self.project.uuid),
            {
                "is_live_desk_copilot": True,
                "parent_uuid": str(self.parent.uuid),
            },
            mode="update",
        )
        self.project.refresh_from_db()
        self.assertTrue(self.project.is_live_desk_copilot)
        self.assertEqual(self.project.parent_project_id, self.parent.uuid)
        self.mock_notify.assert_called_once()

    def test_update_without_keys_does_not_clear_flag(self):
        self.project.is_live_desk_copilot = True
        self.project.parent_project = self.parent
        self.project.save(update_fields=["is_live_desk_copilot", "parent_project"])
        self.usecase.sync(str(self.project.uuid), {"action": "updated"}, mode="update")
        self.project.refresh_from_db()
        self.assertTrue(self.project.is_live_desk_copilot)
        self.assertEqual(self.project.parent_project_id, self.parent.uuid)
        self.mock_notify.assert_not_called()

    def test_update_null_parent_clears_fk(self):
        self.project.parent_project = self.parent
        self.project.save(update_fields=["parent_project"])
        self.usecase.sync(str(self.project.uuid), {"parent_uuid": None}, mode="update")
        self.project.refresh_from_db()
        self.assertIsNone(self.project.parent_project_id)


class SyncVtexInvalidatesCopilotCacheTestCase(TestCase):
    def test_parent_vtex_update_notifies_copilots(self):
        parent = ProjectFactory()
        copilot = ProjectFactory(is_live_desk_copilot=True, parent_project=parent)
        usecase = SyncProjectVtexUseCase()
        with patch("nexus.usecases.projects.sync_vtex.notify_async") as mock_notify:
            usecase.sync_project_vtex(
                str(parent.uuid),
                extract_vtex_fields({"vtex_account": "mainstore", "config": {}}),
                mode="update",
            )
        notified = {call.kwargs["project"].uuid for call in mock_notify.call_args_list}
        self.assertEqual(notified, {parent.uuid, copilot.uuid})


class ProjectUpdateConsumerLiveDeskTestCase(TestCase):
    def test_update_links_parent(self):
        parent = ProjectFactory()
        copilot = ProjectFactory()
        msg = MagicMock()
        msg.body = json.dumps(
            {
                "project_uuid": str(copilot.uuid),
                "action": "updated",
                "is_live_desk_copilot": True,
                "parent_uuid": str(parent.uuid),
            }
        ).encode()
        msg.delivery_tag = 42
        msg.channel = MagicMock()
        ProjectUpdateConsumer().consume(msg)
        copilot.refresh_from_db()
        self.assertTrue(copilot.is_live_desk_copilot)
        self.assertEqual(copilot.parent_project_id, parent.uuid)


class ProjectCreateConsumerLiveDeskTestCase(TestCase):
    def _message(self, payload: dict):
        from weni.eda.messages import Message as WeniMessage

        channel = MagicMock()
        channel.acked = []

        def basic_ack(tag):
            channel.acked.append(tag)

        channel.basic_ack.side_effect = basic_ack
        body = json.dumps(payload).encode()
        amqp_message = MagicMock()
        amqp_message.body = body
        amqp_message.delivery_tag = 7
        amqp_message.channel = channel
        return WeniMessage(body=body, delivery_tag=7, channel=channel), channel

    @patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_create_dto_includes_parent_uuid(self, mock_usecase):
        org = OrgFactory()
        parent = ProjectFactory(org=org, created_by=org.created_by)

        def create_project(project_dto, user_email):
            return ProjectFactory(
                uuid=project_dto.uuid,
                name=project_dto.name,
                org=org,
                created_by=org.created_by,
                is_live_desk_copilot=project_dto.is_live_desk_copilot,
            )

        mock_usecase.return_value.create_project.side_effect = create_project
        project_uuid = str(uuid4())
        msg, channel = self._message(
            {
                "uuid": project_uuid,
                "name": "copilot",
                "organization_uuid": str(org.uuid),
                "user_email": org.created_by.email,
                "is_template": False,
                "template_type_uuid": None,
                "brain_on": False,
                "authorizations": [],
                "is_live_desk_copilot": True,
                "parent_uuid": str(parent.uuid),
            }
        )
        consumer = WeniEDAProjectConsumer()
        consumer._message = msg
        consumer.consume(msg)
        dto = mock_usecase.return_value.create_project.call_args.kwargs["project_dto"]
        self.assertTrue(dto.is_live_desk_copilot)
        self.assertEqual(dto.parent_uuid, str(parent.uuid))
        self.assertEqual(channel.acked, [7])


class PreGenerationCopilotVtexTestCase(SimpleTestCase):
    @patch("router.services.pre_generation_service.manager_pipeline_version_from_project", return_value="new")
    def test_project_to_dict_uses_parent_vtex_for_copilot(self, _mock_pipeline):
        parent = MagicMock()
        parent.vtex_account = "mainstore"
        parent.vtex_host_store = "https://main.example"
        parent.storefront_type = "vtex_io"

        project = MagicMock()
        project.uuid = "copilot-uuid"
        project.agents_backend = "OpenAIBackend"
        project.use_components = False
        project.rationale_switch = False
        project.use_prompt_creation_configurations = False
        project.conversation_turns_to_include = 10
        project.exclude_previous_thinking_steps = True
        project.default_supervisor_foundation_model = None
        project.human_support = False
        project.human_support_prompt = None
        project.default_formatter_foundation_model = None
        project.formatter_instructions = None
        project.formatter_reasoning_effort = None
        project.formatter_reasoning_summary = None
        project.formatter_send_only_assistant_message = False
        project.formatter_tools_descriptions = None
        project.manager_agent = None
        project.is_live_desk_copilot = True
        project.parent_project = parent
        project.parent_project_id = "parent-uuid"
        project.vtex_account = None
        project.vtex_host_store = None
        project.storefront_type = None

        result = PreGenerationService()._project_to_dict(project)
        self.assertEqual(result["vtex_account"], "mainstore")
        self.assertEqual(result["vtex_host_store"], "https://main.example")
        self.assertEqual(result["storefront_type"], "vtex_io")
