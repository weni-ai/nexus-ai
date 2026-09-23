from unittest.mock import AsyncMock, MagicMock, patch

from agents import ModelSettings
from django.test import SimpleTestCase

from inline_agents.backends.openai.adapter import OpenAITeamAdapter
from inline_agents.backends.openai.prompt_cache import (
    COLLABORATOR_CACHE_PROFILE,
    COLLABORATOR_PROMPT_CACHE_KEY,
    MANAGER_CACHE_PROFILE,
    OBJECTIVE_MARKER,
    PROMPT_CACHE_BREAKPOINT,
    PROMPT_CACHE_KEY_PREFIX,
    PROMPT_CACHE_OPTIONS,
    SESSION_CONTEXT_MARKER,
    PromptCachingOpenAIResponsesModel,
    build_cacheable_input,
    build_collaborator_cacheable_input,
    split_cacheable_instructions,
    split_collaborator_cacheable_instructions,
    supports_explicit_prompt_cache,
    with_explicit_cache_settings,
)

GLOBAL_STATIC = "# Manager\n" + ("Always follow the global rules. " * 50)
PROJECT_STATIC = f"{OBJECTIVE_MARKER}\nHelp this project.\n<personality>\nBe concise.\n"
SESSION_CONTEXT = f"{SESSION_CONTEXT_MARKER}\nPROJECT_ID: project-1\nCONTACT_ID: contact-1"
MANAGER_PROMPT = f"{GLOBAL_STATIC}{PROJECT_STATIC}{SESSION_CONTEXT}"
COLLABORATOR_PROMPT = f"{GLOBAL_STATIC}{PROJECT_STATIC}"


class SplitCacheableInstructionsTests(SimpleTestCase):
    def test_splits_at_manager_2_8_markers(self):
        self.assertEqual(
            split_cacheable_instructions(MANAGER_PROMPT),
            (GLOBAL_STATIC, PROJECT_STATIC, SESSION_CONTEXT),
        )

    def test_returns_none_when_objective_marker_is_missing(self):
        self.assertIsNone(split_cacheable_instructions(f"{GLOBAL_STATIC}{SESSION_CONTEXT}"))

    def test_returns_none_when_session_context_marker_is_missing(self):
        self.assertIsNone(split_cacheable_instructions(f"{GLOBAL_STATIC}{PROJECT_STATIC}"))

    def test_returns_none_when_markers_are_out_of_order(self):
        prompt = f"{GLOBAL_STATIC}{SESSION_CONTEXT}{PROJECT_STATIC}"

        self.assertIsNone(split_cacheable_instructions(prompt))


class BuildCacheableInputTests(SimpleTestCase):
    def test_builds_two_breakpoints_and_keeps_session_uncached(self):
        result = build_cacheable_input(MANAGER_PROMPT, "Hello")

        self.assertIsNotNone(result)
        input_items, cache_key = result
        developer_message = input_items[0]
        content = developer_message["content"]

        self.assertEqual(developer_message["role"], "developer")
        self.assertEqual(content[0]["text"], GLOBAL_STATIC)
        self.assertEqual(content[0]["prompt_cache_breakpoint"], PROMPT_CACHE_BREAKPOINT)
        self.assertEqual(content[1]["text"], PROJECT_STATIC)
        self.assertEqual(content[1]["prompt_cache_breakpoint"], PROMPT_CACHE_BREAKPOINT)
        self.assertEqual(content[2], {"type": "input_text", "text": SESSION_CONTEXT})
        self.assertEqual(input_items[1], {"role": "user", "content": "Hello"})
        self.assertEqual(cache_key, PROMPT_CACHE_KEY_PREFIX)

    def test_prepends_developer_message_to_existing_conversation(self):
        history = [{"role": "user", "content": "Previous turn"}]

        result = build_cacheable_input(MANAGER_PROMPT, history)

        self.assertIsNotNone(result)
        input_items, _ = result
        self.assertEqual(input_items[1:], history)

    def test_cache_key_is_stable_across_projects_and_sessions(self):
        _, first_key = build_cacheable_input(MANAGER_PROMPT, "Hello")
        _, second_key = build_cacheable_input(
            MANAGER_PROMPT.replace("Help this project.", "Help another project.").replace(
                "CONTACT_ID: contact-1",
                "CONTACT_ID: contact-2",
            ),
            "Hello",
        )

        self.assertEqual(first_key, second_key)


class CollaboratorCacheableInputTests(SimpleTestCase):
    def test_splits_only_at_objective_marker(self):
        self.assertEqual(
            split_collaborator_cacheable_instructions(COLLABORATOR_PROMPT),
            (GLOBAL_STATIC, PROJECT_STATIC),
        )

    def test_returns_none_when_objective_marker_is_missing(self):
        self.assertIsNone(split_collaborator_cacheable_instructions(GLOBAL_STATIC))

    def test_builds_two_breakpoints_and_keeps_question_as_user_input(self):
        result = build_collaborator_cacheable_input(COLLABORATOR_PROMPT, "Where is order 1001?")

        self.assertIsNotNone(result)
        input_items, cache_key = result
        content = input_items[0]["content"]

        self.assertEqual(content[0]["text"], GLOBAL_STATIC)
        self.assertEqual(content[0]["prompt_cache_breakpoint"], PROMPT_CACHE_BREAKPOINT)
        self.assertEqual(content[1]["text"], PROJECT_STATIC)
        self.assertEqual(content[1]["prompt_cache_breakpoint"], PROMPT_CACHE_BREAKPOINT)
        self.assertEqual(input_items[1], {"role": "user", "content": "Where is order 1001?"})
        self.assertEqual(cache_key, COLLABORATOR_PROMPT_CACHE_KEY)

    def test_prepends_developer_message_to_existing_conversation(self):
        history = [{"role": "user", "content": "Previous manager question"}]

        result = build_collaborator_cacheable_input(COLLABORATOR_PROMPT, history)

        self.assertIsNotNone(result)
        input_items, _ = result
        self.assertEqual(input_items[1:], history)


class ExplicitCacheSettingsTests(SimpleTestCase):
    def test_adds_cache_settings_without_removing_existing_settings(self):
        settings = ModelSettings(
            extra_body={"existing_body": True},
            extra_args={"store": False},
        )

        result = with_explicit_cache_settings(settings, "cache-key")

        self.assertEqual(
            result.extra_body,
            {
                "existing_body": True,
                "prompt_cache_options": PROMPT_CACHE_OPTIONS,
            },
        )
        self.assertEqual(
            result.extra_args,
            {
                "store": False,
                "prompt_cache_key": "cache-key",
            },
        )

    def test_preserves_explicit_overrides(self):
        settings = ModelSettings(
            extra_body={"prompt_cache_options": {"mode": "implicit"}},
            extra_args={"prompt_cache_key": "custom-key"},
        )

        result = with_explicit_cache_settings(settings, "generated-key")

        self.assertEqual(result.extra_body["prompt_cache_options"], {"mode": "implicit"})
        self.assertEqual(result.extra_args["prompt_cache_key"], "custom-key")

    def test_does_not_mutate_original_settings(self):
        settings = ModelSettings(extra_args={"store": False})

        with_explicit_cache_settings(settings, "cache-key")

        self.assertEqual(settings.extra_args, {"store": False})
        self.assertIsNone(settings.extra_body)


class PromptCachingOpenAIResponsesModelTests(SimpleTestCase):
    def test_prepare_moves_instructions_into_input_and_adds_settings(self):
        model = PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")

        instructions, input_items, settings = model._prepare(
            MANAGER_PROMPT,
            "Hello",
            ModelSettings(extra_args={"store": False}),
        )

        self.assertIsNone(instructions)
        self.assertEqual(input_items[0]["role"], "developer")
        self.assertEqual(settings.extra_body["prompt_cache_options"], PROMPT_CACHE_OPTIONS)
        self.assertFalse(settings.extra_args["store"])
        self.assertEqual(settings.extra_args["prompt_cache_key"], PROMPT_CACHE_KEY_PREFIX)

    def test_prepare_falls_back_to_uncached_prompt_when_markers_are_missing(self):
        model = PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")
        settings = ModelSettings(extra_args={"store": False})

        instructions, input_items, resulting_settings = model._prepare(
            "Prompt without markers",
            "Hello",
            settings,
        )

        self.assertEqual(instructions, "Prompt without markers")
        self.assertEqual(input_items, "Hello")
        self.assertIs(resulting_settings, settings)

    def test_missing_markers_warns_once_per_model(self):
        from inline_agents.backends.openai import prompt_cache

        model = PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")
        warning_key = (model.model, MANAGER_CACHE_PROFILE)
        prompt_cache._warned_models.discard(warning_key)

        with self.assertLogs(prompt_cache.logger.name, level="WARNING") as captured:
            model._prepare("Prompt without markers", "Hello", ModelSettings())
            model._prepare("Prompt without markers", "Hello", ModelSettings())

        self.assertEqual(len(captured.records), 1)
        prompt_cache._warned_models.discard(warning_key)

    def test_collaborator_profile_uses_objective_only_layout(self):
        model = PromptCachingOpenAIResponsesModel(
            "openai.gpt-5.6-luna",
            cache_profile=COLLABORATOR_CACHE_PROFILE,
        )

        instructions, input_items, settings = model._prepare(
            COLLABORATOR_PROMPT,
            "Where is order 1001?",
            ModelSettings(),
        )

        self.assertIsNone(instructions)
        self.assertEqual(len(input_items[0]["content"]), 2)
        self.assertEqual(input_items[1]["role"], "user")
        self.assertEqual(settings.extra_args["prompt_cache_key"], COLLABORATOR_PROMPT_CACHE_KEY)

    def test_collaborator_missing_objective_falls_back_without_manager_layout(self):
        model = PromptCachingOpenAIResponsesModel(
            "openai.gpt-5.6-luna",
            cache_profile=COLLABORATOR_CACHE_PROFILE,
        )
        settings = ModelSettings()

        instructions, input_items, resulting_settings = model._prepare(
            "Prompt without marker",
            "Hello",
            settings,
        )

        self.assertEqual(instructions, "Prompt without marker")
        self.assertEqual(input_items, "Hello")
        self.assertIs(resulting_settings, settings)

    def test_manager_and_collaborator_missing_marker_warnings_are_independent(self):
        from inline_agents.backends.openai import prompt_cache

        model_name = "openai.gpt-5.6-luna"
        manager_key = (model_name, MANAGER_CACHE_PROFILE)
        collaborator_key = (model_name, COLLABORATOR_CACHE_PROFILE)
        prompt_cache._warned_models.discard(manager_key)
        prompt_cache._warned_models.discard(collaborator_key)

        manager = PromptCachingOpenAIResponsesModel(model_name)
        collaborator = PromptCachingOpenAIResponsesModel(
            model_name,
            cache_profile=COLLABORATOR_CACHE_PROFILE,
        )

        with self.assertLogs(prompt_cache.logger.name, level="WARNING") as captured:
            manager._prepare("Prompt without markers", "Hello", ModelSettings())
            collaborator._prepare("Prompt without markers", "Hello", ModelSettings())

        self.assertEqual(len(captured.records), 2)
        prompt_cache._warned_models.discard(manager_key)
        prompt_cache._warned_models.discard(collaborator_key)

    def test_prepare_keeps_empty_instructions_unchanged(self):
        model = PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")
        settings = ModelSettings()

        instructions, input_items, resulting_settings = model._prepare(None, "Hello", settings)

        self.assertIsNone(instructions)
        self.assertEqual(input_items, "Hello")
        self.assertIs(resulting_settings, settings)

    @patch("inline_agents.backends.openai.prompt_cache.get_default_openai_client")
    def test_model_does_not_bind_client_until_first_use(self, get_client):
        PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")

        get_client.assert_not_called()

    @patch("inline_agents.backends.openai.prompt_cache.get_default_openai_client", return_value=None)
    def test_model_requires_configured_default_client(self, _get_client):
        model = PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")

        with self.assertRaisesRegex(RuntimeError, "default OpenAI client"):
            model._model()

    @patch("inline_agents.backends.openai.prompt_cache.OpenAIResponsesModel")
    @patch("inline_agents.backends.openai.prompt_cache.get_default_openai_client")
    def test_model_retains_request_scoped_client(self, get_client, responses_model):
        client = MagicMock()
        resolved_model = MagicMock()
        get_client.return_value = client
        responses_model.return_value = resolved_model
        model = PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")

        self.assertIs(model._model(), resolved_model)
        self.assertIs(model._model(), resolved_model)

        responses_model.assert_called_once_with(model="openai.gpt-5.6-luna", openai_client=client)

    async def test_get_response_forwards_rewritten_prompt_and_settings(self):
        model = PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")
        delegate = MagicMock()
        delegate.get_response = AsyncMock(return_value=MagicMock())

        with patch.object(model, "_model", return_value=delegate):
            await model.get_response(
                MANAGER_PROMPT,
                "Hello",
                ModelSettings(extra_args={"store": False}),
                [],
                None,
                [],
                MagicMock(),
                previous_response_id=None,
                conversation_id=None,
                prompt=None,
            )

        args = delegate.get_response.await_args.args
        self.assertIsNone(args[0])
        self.assertEqual(args[1][0]["role"], "developer")
        self.assertEqual(args[2].extra_body["prompt_cache_options"], PROMPT_CACHE_OPTIONS)
        self.assertFalse(args[2].extra_args["store"])
        self.assertEqual(args[2].extra_args["prompt_cache_key"], PROMPT_CACHE_KEY_PREFIX)

    async def test_stream_response_forwards_rewritten_prompt_and_settings(self):
        model = PromptCachingOpenAIResponsesModel("openai.gpt-5.6-luna")
        delegate = MagicMock()
        captured = {}

        async def stream_response(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            yield MagicMock()

        delegate.stream_response = stream_response
        with patch.object(model, "_model", return_value=delegate):
            events = [
                event
                async for event in model.stream_response(
                    MANAGER_PROMPT,
                    "Hello",
                    ModelSettings(),
                    [],
                    None,
                    [],
                    MagicMock(),
                    previous_response_id=None,
                    conversation_id=None,
                    prompt=None,
                )
            ]

        self.assertEqual(len(events), 1)
        self.assertIsNone(captured["args"][0])
        self.assertEqual(captured["args"][1][0]["role"], "developer")
        self.assertEqual(captured["args"][2].extra_body["prompt_cache_options"], PROMPT_CACHE_OPTIONS)


class SupportsExplicitPromptCacheTests(SimpleTestCase):
    def test_supports_manager_2_8_luna_on_aws_mantle(self):
        self.assertTrue(supports_explicit_prompt_cache("openai.gpt-5.6-luna", "AWS_MANTLE"))

    def test_rejects_other_models_and_vendors(self):
        self.assertFalse(supports_explicit_prompt_cache("openai.gpt-5.6-sol", "aws_mantle"))
        self.assertFalse(supports_explicit_prompt_cache("openai.gpt-5.6-luna", "openai"))
        self.assertFalse(supports_explicit_prompt_cache("openai.gpt-5.6-luna", None))


class PromptCacheAdapterWiringTests(SimpleTestCase):
    @patch("inline_agents.backends.openai.adapter.SupervisorEntity")
    @patch.object(OpenAITeamAdapter, "_get_context", return_value=MagicMock())
    @patch.object(OpenAITeamAdapter, "_get_tools", return_value=[])
    @patch.object(OpenAITeamAdapter, "build_agents", return_value=[])
    @patch.object(OpenAITeamAdapter, "get_supervisor_instructions", return_value=MANAGER_PROMPT)
    def test_passes_model_vendor_to_manager_entity(
        self,
        _get_instructions,
        _build_agents,
        _get_tools,
        _get_context,
        supervisor_entity,
    ):
        manager = MagicMock()
        manager.knowledge_base_bedrock.name = "knowledge_base_bedrock"
        supervisor_entity.return_value = manager
        supervisor_hooks = MagicMock()
        supervisor = {
            "instruction": MANAGER_PROMPT,
            "foundation_model": "openai.gpt-5.6-luna",
            "model_vendor": "aws_mantle",
            "model_settings": {},
            "max_tokens": {},
            "tools": [],
            "user_model_credentials": {},
            "collaborator_configurations": {},
        }

        OpenAITeamAdapter.to_external_enhanced(
            supervisor=supervisor,
            agents=[],
            content_base_uuid="content-base",
            instructions=[],
            contact_urn="contact",
            contact_name="Customer",
            project_uuid="project",
            channel_uuid="channel",
            contact_fields="",
            business_rules="",
            use_components=False,
            agent_data={},
            data_lake_event_adapter=MagicMock(),
            hooks_state=MagicMock(),
            event_manager_notify=MagicMock(),
            preview=False,
            preview_websocket=False,
            rationale_switch=False,
            language="en",
            user_email="user@example.com",
            supervisor_hooks=supervisor_hooks,
            input_text="Hello",
            auth_token="token",
            session=MagicMock(),
            session_factory=MagicMock(),
            session_id="session",
            msg_external_id="message",
            turn_off_rationale=False,
        )

        self.assertEqual(supervisor_entity.call_args.kwargs["model_vendor"], "aws_mantle")
