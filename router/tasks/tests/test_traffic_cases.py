from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.tasks.invoke import (
    apply_simulation_foundation_model_override,
    effective_simulation_channel,
    should_skip_conversation_sqs,
)


class TrafficCaseHelpersTestCase(SimpleTestCase):
    def test_effective_simulation_channel_explicit_kwarg(self):
        msg = {"project_uuid": "p1", "channel_uuid": None}
        self.assertTrue(effective_simulation_channel(msg, simulation_channel=True))

    def test_effective_simulation_channel_invalid_project_uuid_no_db(self):
        msg = {"project_uuid": "proj-123", "channel_uuid": "x"}
        self.assertFalse(effective_simulation_channel(msg, simulation_channel=False))

    def test_should_skip_conversation_sqs_preview_only(self):
        self.assertTrue(should_skip_conversation_sqs(preview=True, simulation_channel_effective=False))

    def test_should_skip_conversation_sqs_simulation_channel_only(self):
        self.assertTrue(should_skip_conversation_sqs(preview=False, simulation_channel_effective=True))

    def test_should_skip_conversation_sqs_neither(self):
        self.assertFalse(should_skip_conversation_sqs(preview=False, simulation_channel_effective=False))

    def test_apply_simulation_override_skipped_when_simulation_false(self):
        self.assertEqual(
            apply_simulation_foundation_model_override(False, "p1", "urn:x", "base"),
            "base",
        )

    @patch("router.tasks.invoke._get_simulation_manager_model")
    def test_apply_simulation_override_uses_cache(self, mock_get):
        mock_get.return_value = "from-redis"
        self.assertEqual(
            apply_simulation_foundation_model_override(True, "p1", "urn:x", "base"),
            "from-redis",
        )


class StartInlineAgentsSqsGatingTestCase(SimpleTestCase):
    def test_case3_skips_sqs_when_default_channel_matches(self):
        from router.tasks.invoke import start_inline_agents

        producer = MagicMock()
        default_ch = "11111111-1111-1111-1111-111111111111"
        message = {
            "project_uuid": "22222222-2222-2222-2222-222222222222",
            "text": "hello",
            "contact_urn": "ext:user@example.com",
            "channel_uuid": default_ch,
            "metadata": {},
            "attachments": [],
        }

        mock_pre_gen = MagicMock()
        mock_pre_gen.fetch_pre_generation_data.return_value = (
            {"use_components": False},
            {},
            {},
            {},
            {},
            "openai",
            {},
            {},
        )

        with patch("router.tasks.invoke.settings.WORKFLOW_ARCHITECTURE_PROJECTS", []):
            with patch("router.tasks.invoke.get_task_manager", return_value=MagicMock()):
                with patch("router.tasks.invoke.notify_async"):
                    with patch("router.tasks.invoke.TypingUsecase.send_typing_message"):
                        with patch(
                            "router.tasks.invoke.PreGenerationService",
                            return_value=mock_pre_gen,
                        ):
                            with patch(
                                "router.tasks.invoke.get_action_clients",
                                return_value=({}, None),
                            ):
                                with patch(
                                    "router.tasks.invoke._preprocess_message_input",
                                    return_value=(message, None, False),
                                ):
                                    with patch(
                                        "router.tasks.invoke._manage_pending_task",
                                        return_value="hello",
                                    ):
                                        with patch(
                                            "router.tasks.invoke.CachedProjectData.from_pre_generation_data",
                                            return_value=MagicMock(),
                                        ):
                                            with patch(
                                                "router.tasks.invoke.BackendsRegistry.get_backend",
                                                return_value=MagicMock(),
                                            ):
                                                with patch(
                                                    "router.tasks.invoke._invoke_backend",
                                                    return_value=("ok", True),
                                                ):
                                                    with patch(
                                                        "router.tasks.invoke.channel_matches_default_preview",
                                                        return_value=True,
                                                    ):
                                                        with patch(
                                                            "router.tasks.invoke.get_conversation_events_producer",
                                                            return_value=producer,
                                                        ):
                                                            start_inline_agents.run(
                                                                message=message,
                                                                preview=False,
                                                                simulation=False,
                                                                simulation_channel=False,
                                                            )

        producer.send_event.assert_not_called()
