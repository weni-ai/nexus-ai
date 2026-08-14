from django.test import SimpleTestCase

from nexus.projects.channel_ops import (
    MAILROOM_FLOW_SIMULATOR_CHANNEL_UUID,
    MAILROOM_FLOW_SIMULATOR_CONTACT_URN,
)
from router.tasks.invoke import effective_simulation_channel, should_skip_conversation_sqs


class SimulationSqsGatingTests(SimpleTestCase):
    def test_simulator_contact_urn_is_effective_simulation_channel(self) -> None:
        message = {
            "project_uuid": "invalid",
            "contact_urn": MAILROOM_FLOW_SIMULATOR_CONTACT_URN,
        }

        self.assertTrue(effective_simulation_channel(message))

    def test_simulator_channel_uuid_is_effective_simulation_channel(self) -> None:
        message = {
            "project_uuid": "invalid",
            "channel_uuid": MAILROOM_FLOW_SIMULATOR_CHANNEL_UUID,
        }

        self.assertTrue(effective_simulation_channel(message))

    def test_explicit_simulation_channel_takes_precedence(self) -> None:
        self.assertTrue(effective_simulation_channel({}, simulation_channel=True))

    def test_regular_traffic_is_not_effective_simulation_channel(self) -> None:
        message = {
            "project_uuid": "invalid",
            "contact_urn": "tel:+5511999999999",
            "channel_uuid": "8d38af30-a40c-4664-95e4-a7c132948140",
        }

        self.assertFalse(effective_simulation_channel(message))

    def test_skip_conversation_sqs_for_preview_or_simulation(self) -> None:
        cases = [
            (False, False, False),
            (True, False, True),
            (False, True, True),
            (True, True, True),
        ]

        for preview, simulation_channel, expected in cases:
            with self.subTest(preview=preview, simulation_channel=simulation_channel):
                self.assertEqual(
                    should_skip_conversation_sqs(preview, simulation_channel),
                    expected,
                )
