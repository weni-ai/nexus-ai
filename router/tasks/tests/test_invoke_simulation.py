from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.tasks.invoke import start_inline_agents


class StartInlineAgentsSimulationOverrideTestCase(SimpleTestCase):
    @patch("router.tasks.invoke.dispatch_with_optional_builder_websocket")
    @patch("router.tasks.invoke.notify_async")
    @patch("router.tasks.invoke._invoke_backend")
    @patch("router.tasks.invoke.BackendsRegistry.get_backend")
    @patch("router.tasks.invoke.CachedProjectData.from_pre_generation_data")
    @patch("router.tasks.invoke._manage_pending_task")
    @patch("router.tasks.invoke._preprocess_message_input")
    @patch("router.tasks.invoke.get_action_clients")
    @patch("router.tasks.invoke.PreGenerationService.fetch_pre_generation_data")
    @patch("router.tasks.invoke.TypingUsecase.send_typing_message")
    @patch("router.tasks.invoke._get_simulation_manager_model")
    def test_simulation_uses_cached_foundation_model(
        self,
        mock_get_simulation_manager_model,
        _mock_typing,
        mock_pre_generation,
        mock_get_action_clients,
        mock_preprocess,
        mock_manage_pending_task,
        mock_cached_context,
        mock_get_backend,
        mock_invoke_backend,
        _mock_notify,
        _mock_dispatch,
    ):
        with patch("router.tasks.invoke.settings.WORKFLOW_ARCHITECTURE_PROJECTS", [], create=True):
            message = {
                "project_uuid": "proj-1",
                "text": "hello",
                "contact_urn": "ext:user@example.com",
                "metadata": {},
                "attachments": [],
            }
            mock_get_simulation_manager_model.return_value = "override-model"
            mock_pre_generation.return_value = ({}, {}, {}, {}, {}, "openai", {}, {})
            mock_get_action_clients.return_value = ({}, None)
            mock_preprocess.return_value = (message, "default-model", False)
            mock_manage_pending_task.return_value = "hello"
            mock_cached_context.return_value = MagicMock()
            mock_get_backend.return_value = MagicMock()
            mock_invoke_backend.return_value = ("ok", True)

            start_inline_agents.run(message=message, preview=True, simulation=True)

            mock_get_simulation_manager_model.assert_called_once_with("proj-1")
            self.assertEqual(mock_invoke_backend.call_args.kwargs["foundation_model"], "override-model")

    @patch("router.tasks.invoke.dispatch_with_optional_builder_websocket")
    @patch("router.tasks.invoke.notify_async")
    @patch("router.tasks.invoke._invoke_backend")
    @patch("router.tasks.invoke.BackendsRegistry.get_backend")
    @patch("router.tasks.invoke.CachedProjectData.from_pre_generation_data")
    @patch("router.tasks.invoke._manage_pending_task")
    @patch("router.tasks.invoke._preprocess_message_input")
    @patch("router.tasks.invoke.get_action_clients")
    @patch("router.tasks.invoke.PreGenerationService.fetch_pre_generation_data")
    @patch("router.tasks.invoke.TypingUsecase.send_typing_message")
    @patch("router.tasks.invoke._get_simulation_manager_model")
    def test_preview_does_not_use_simulation_override(
        self,
        mock_get_simulation_manager_model,
        _mock_typing,
        mock_pre_generation,
        mock_get_action_clients,
        mock_preprocess,
        mock_manage_pending_task,
        mock_cached_context,
        mock_get_backend,
        mock_invoke_backend,
        _mock_notify,
        _mock_dispatch,
    ):
        with patch("router.tasks.invoke.settings.WORKFLOW_ARCHITECTURE_PROJECTS", [], create=True):
            message = {
                "project_uuid": "proj-1",
                "text": "hello",
                "contact_urn": "ext:user@example.com",
                "metadata": {},
                "attachments": [],
            }
            mock_pre_generation.return_value = ({}, {}, {}, {}, {}, "openai", {}, {})
            mock_get_action_clients.return_value = ({}, None)
            mock_preprocess.return_value = (message, "default-model", False)
            mock_manage_pending_task.return_value = "hello"
            mock_cached_context.return_value = MagicMock()
            mock_get_backend.return_value = MagicMock()
            mock_invoke_backend.return_value = ("ok", True)

            start_inline_agents.run(message=message, preview=True, simulation=False)

            mock_get_simulation_manager_model.assert_not_called()
            self.assertEqual(mock_invoke_backend.call_args.kwargs["foundation_model"], "default-model")
