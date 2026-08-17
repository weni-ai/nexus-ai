from unittest.mock import patch

import pendulum
from django.test import TestCase
from weni_commons.change_history import Action, Entity, Module, Notifier

from nexus.event_domain.recent_activity.create import create_recent_activity
from nexus.event_domain.recent_activity.publishers_dto import RecentActivitiesDTO
from nexus.event_domain.recent_activity.recent_activities_dto import CreateRecentActivityDTO
from nexus.event_domain.recent_activity.recent_activity_amq import (
    _values_from_details,
    notify_change,
    publish_external_recent_activity_to_amq,
    publish_recent_activity_to_amq,
)
from nexus.logs.models import RecentActivities
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseLinkFactory, IntelligenceFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class ValuesFromDetailsTestCase(TestCase):
    def test_flat_old_new_shape(self):
        old_value, new_value = _values_from_details({"old": "", "new": "template"})
        self.assertIsNone(old_value)
        self.assertEqual(new_value, "template")

    def test_single_nested_field(self):
        old_value, new_value = _values_from_details({"name": {"old": "a", "new": "b"}})
        self.assertEqual(old_value, "a")
        self.assertEqual(new_value, "b")

    def test_multi_field_prefers_text_over_metadata(self):
        old_value, new_value = _values_from_details(
            {
                "modified_by": {"old": None, "new": 23},
                "modified_at": {"old": None, "new": "2026-08-14 17:40:17.280556+00:00"},
                "text": {"old": "olaaaaaaaaaaaaa", "new": "olaaaaaaaaaaaaahmmmmmm"},
                "last_updated_at": {"old": None, "new": "2026-08-14 17:40:17.280556+00:00"},
            }
        )
        self.assertEqual(old_value, "olaaaaaaaaaaaaa")
        self.assertEqual(new_value, "olaaaaaaaaaaaaahmmmmmm")

    def test_empty_details(self):
        self.assertEqual(_values_from_details(None), (None, None))
        self.assertEqual(_values_from_details({}), (None, None))


class RecentActivityAmqTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.intelligence = IntelligenceFactory(created_by=self.project.created_by, org=self.project.org)

    def tearDown(self) -> None:
        from weni.eda.connection import EDAConnection

        EDAConnection.clear_connection()

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAConnection.clear_connection")
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.Notifier.notify_change")
    def test_notify_change_maps_brain_on_to_project_entity(self, mock_notifier, mock_clear_connection):
        date = pendulum.datetime(2026, 5, 20, 11, 15, 0, tz="UTC")

        notify_change(
            project_uuid=str(self.project.uuid),
            user_email=self.project.created_by.email,
            date=date,
            action="UPDATE",
            entity="brain_on",
            object_id=str(self.project.uuid),
            object_name="brain_on",
            old_value="False",
            new_value="True",
        )

        mock_notifier.assert_called_once()
        mock_clear_connection.assert_called_once()
        kwargs = mock_notifier.call_args.kwargs
        self.assertEqual(kwargs["project_uuid"], str(self.project.uuid))
        self.assertEqual(kwargs["user_email"], self.project.created_by.email)
        self.assertEqual(kwargs["date"], date)
        self.assertEqual(kwargs["action"], Action.UPDATE)
        self.assertEqual(kwargs["entity"], Entity.PROJECT)
        self.assertEqual(kwargs["module"], Module.NEXUS)
        self.assertEqual(kwargs["object_id"], str(self.project.uuid))
        self.assertEqual(kwargs["object_name"], "brain_on")
        self.assertEqual(kwargs["old_value"], "False")
        self.assertEqual(kwargs["new_value"], "True")

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAConnection.clear_connection")
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.Notifier.notify_change")
    def test_notify_change_maps_content_base_entity(self, mock_notifier, mock_clear_connection):
        notify_change(
            project_uuid=str(self.project.uuid),
            user_email=self.project.created_by.email,
            date=pendulum.now("UTC"),
            action="C",
            entity="ContentBase",
            object_name="ContentBase",
        )

        kwargs = mock_notifier.call_args.kwargs
        self.assertEqual(kwargs["entity"], Entity.CONTENT_BASE)
        self.assertEqual(kwargs["module"], Module.KNOWLEDGE_BASE)
        mock_clear_connection.assert_called_once()

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAConnection.clear_connection")
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.Notifier.notify_change")
    def test_notify_change_maps_instruction_to_instructions_module(self, mock_notifier, mock_clear_connection):
        notify_change(
            project_uuid=str(self.project.uuid),
            user_email=self.project.created_by.email,
            date=pendulum.now("UTC"),
            action="C",
            entity="ContentBaseInstruction",
            object_name="Always greet the customer",
        )

        kwargs = mock_notifier.call_args.kwargs
        self.assertEqual(kwargs["entity"], Entity.CONTENT_BASE_INSTRUCTION)
        self.assertEqual(kwargs["module"], Module.INSTRUCTIONS)
        mock_clear_connection.assert_called_once()

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAConnection.clear_connection")
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.Notifier.notify_change")
    def test_notify_change_maps_agent_to_my_agents_module(self, mock_notifier, mock_clear_connection):
        notify_change(
            project_uuid=str(self.project.uuid),
            user_email=self.project.created_by.email,
            date=pendulum.now("UTC"),
            action="C",
            entity="ContentBaseAgent",
            object_name="Product Concierge",
        )

        kwargs = mock_notifier.call_args.kwargs
        self.assertEqual(kwargs["entity"], Entity.CONTENT_BASE_AGENT)
        self.assertEqual(kwargs["module"], Module.MY_AGENTS)
        mock_clear_connection.assert_called_once()

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAConnection.clear_connection")
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.Notifier.notify_change")
    def test_notify_change_maps_inline_agent_to_my_agents_module(self, mock_notifier, mock_clear_connection):
        notify_change(
            project_uuid=str(self.project.uuid),
            user_email=self.project.created_by.email,
            date=pendulum.now("UTC"),
            action="C",
            entity="Agent",
            object_name="Product Concierge",
        )

        kwargs = mock_notifier.call_args.kwargs
        self.assertEqual(kwargs["entity"], Entity.AGENT)
        self.assertEqual(kwargs["module"], Module.MY_AGENTS)
        mock_clear_connection.assert_called_once()

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAConnection.clear_connection")
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.Notifier.notify_change")
    def test_notify_change_maps_link_to_knowledge_base_module(self, mock_notifier, mock_clear_connection):
        notify_change(
            project_uuid=str(self.project.uuid),
            user_email=self.project.created_by.email,
            date=pendulum.now("UTC"),
            action="ADD",
            entity="ContentBaseLink",
            object_name="https://test.com",
        )

        kwargs = mock_notifier.call_args.kwargs
        self.assertEqual(kwargs["entity"], Entity.CONTENT_BASE_LINK)
        self.assertEqual(kwargs["module"], Module.KNOWLEDGE_BASE)
        mock_clear_connection.assert_called_once()

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.Notifier.notify_change")
    def test_notify_change_skips_when_project_uuid_missing(self, mock_notifier):
        notify_change(
            project_uuid="",
            user_email=self.project.created_by.email,
            date=pendulum.now("UTC"),
            action="UPDATE",
            entity="Project",
        )
        mock_notifier.assert_not_called()

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.notify_change")
    def test_publish_recent_activity_maps_to_notify_change(self, mock_notify_change):
        recent_activity = RecentActivities.objects.create(
            action_model="ContentBase",
            action_type="U",
            project=self.project,
            created_by=self.project.created_by,
            intelligence=self.intelligence,
            action_details={"name": {"old": "a", "new": "b"}},
        )

        publish_recent_activity_to_amq(recent_activity=recent_activity)

        mock_notify_change.assert_called_once()
        kwargs = mock_notify_change.call_args.kwargs
        self.assertEqual(kwargs["project_uuid"], str(self.project.uuid))
        self.assertEqual(kwargs["user_email"], self.project.created_by.email)
        self.assertEqual(kwargs["action"], "U")
        self.assertEqual(kwargs["entity"], "ContentBase")
        self.assertEqual(kwargs["object_name"], "ContentBase")
        self.assertEqual(kwargs["object_id"], str(recent_activity.uuid))
        self.assertEqual(kwargs["old_value"], "a")
        self.assertEqual(kwargs["new_value"], "b")

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.notify_change")
    def test_publish_recent_activity_uses_instance_display_name(self, mock_notify_change):
        recent_activity = RecentActivities.objects.create(
            action_model="ContentBaseLink",
            action_type="C",
            project=self.project,
            created_by=self.project.created_by,
            intelligence=self.intelligence,
            action_details={},
        )
        link = ContentBaseLinkFactory(
            link="https://test.com",
            content_base__intelligence=self.intelligence,
            content_base__created_by=self.project.created_by,
        )

        publish_recent_activity_to_amq(recent_activity=recent_activity, instance=link)

        kwargs = mock_notify_change.call_args.kwargs
        self.assertEqual(kwargs["entity"], "ContentBaseLink")
        self.assertEqual(kwargs["object_name"], "https://test.com")
        self.assertEqual(kwargs["object_id"], str(link.uuid))

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.notify_change")
    def test_publish_external_fans_out_per_project(self, mock_notify_change):
        dto = RecentActivitiesDTO(
            org=self.project.org,
            user=self.project.created_by,
            entity_name="My Intelligence",
            action="DELETE",
            action_model="Intelligence",
        )

        publish_external_recent_activity_to_amq(dto)

        self.assertEqual(mock_notify_change.call_count, self.project.org.projects.count())
        kwargs = mock_notify_change.call_args.kwargs
        self.assertEqual(kwargs["project_uuid"], str(self.project.uuid))
        self.assertEqual(kwargs["entity"], "Intelligence")
        self.assertEqual(kwargs["object_name"], "My Intelligence")

    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_create_publishes_to_amq(self, mock_publish):
        dto = CreateRecentActivityDTO(
            action_type="C",
            project=self.project,
            created_by=self.project.created_by,
            intelligence=self.intelligence,
            action_details={},
        )

        recent_activity = create_recent_activity(instance=self.intelligence, dto=dto)

        self.assertEqual(RecentActivities.objects.count(), 1)
        mock_publish.assert_called_once_with(recent_activity=recent_activity, instance=self.intelligence)

    def test_notifier_exchange_matches_contract(self):
        self.assertEqual(Notifier.EXCHANGE, "change-history.topic")

    def test_new_nexus_entities_exist_in_weni_commons(self):
        self.assertEqual(Entity.CONTENT_BASE.value, "CONTENT_BASE")
        self.assertEqual(Entity.INTELLIGENCE.value, "INTELLIGENCE")
        self.assertEqual(Entity.LLM.value, "LLM")
        self.assertEqual(Entity.PROJECT.value, "PROJECT")
        self.assertEqual(Entity.FLOW.value, "FLOW")
        self.assertEqual(Entity.AGENT.value, "AGENT")
        self.assertEqual(Module.KNOWLEDGE_BASE.value, "KNOWLEDGE_BASE")
        self.assertEqual(Module.INSTRUCTIONS.value, "INSTRUCTIONS")
        self.assertEqual(Module.MY_AGENTS.value, "MY_AGENTS")
