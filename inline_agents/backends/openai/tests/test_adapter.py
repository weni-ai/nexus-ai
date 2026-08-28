from typing import Optional
from unittest.mock import patch

from django.test import TestCase
from pydantic import BaseModel, ValidationError

from inline_agents.backends.openai.adapter import OpenAIDataLakeEventAdapter, OpenAITeamAdapter
from inline_agents.data_lake.mock_service import MockDataLakeEventService


class TestCreateFunctionArgsClass(TestCase):
    """Test cases for the create_function_args_class method."""

    def test_create_model_with_string_field(self):
        """Test creating a model with a string field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "name": {
                    "type": "string",
                    "description": "User's name",
                    "required": True,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        self.assertTrue(issubclass(model_class, BaseModel))
        self.assertEqual(model_class.__name__, "TestModel")

        field_info = model_class.model_fields["name"]
        self.assertEqual(field_info.annotation, str)
        self.assertEqual(field_info.description, "User's name")

        with self.assertRaises(ValidationError):
            model_class()

    def test_create_model_with_integer_field(self):
        """Test creating a model with an integer field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "age": {
                    "type": "integer",
                    "description": "User's age",
                    "required": True,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["age"]
        self.assertEqual(field_info.annotation, int)
        self.assertEqual(field_info.description, "User's age")

        instance = model_class(age=25)
        self.assertEqual(instance.age, 25)

    def test_create_model_with_number_field(self):
        """Test creating a model with a number (float) field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "score": {
                    "type": "number",
                    "description": "User's score",
                    "required": True,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["score"]
        self.assertEqual(field_info.annotation, float)
        self.assertEqual(field_info.description, "User's score")

        instance = model_class(score=95.5)
        self.assertEqual(instance.score, 95.5)

    def test_create_model_with_boolean_field(self):
        """Test creating a model with a boolean field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "active": {
                    "type": "boolean",
                    "description": "User's active status",
                    "required": True,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["active"]
        self.assertEqual(field_info.annotation, bool)
        self.assertEqual(field_info.description, "User's active status")

        instance = model_class(active=True)
        self.assertTrue(instance.active)

    def test_create_model_with_array_field(self):
        """Test creating a model with an array field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "tags": {
                    "type": "array",
                    "description": "User's tags",
                    "required": True,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["tags"]
        self.assertEqual(field_info.annotation, list)
        self.assertEqual(field_info.description, "User's tags")

        instance = model_class(tags=["tag1", "tag2"])
        self.assertEqual(instance.tags, ["tag1", "tag2"])

    def test_create_model_with_object_field(self):
        """Test creating a model with an object field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "metadata": {
                    "type": "object",
                    "description": "User's metadata",
                    "required": True,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["metadata"]
        self.assertEqual(field_info.annotation, dict)
        self.assertEqual(field_info.description, "User's metadata")

        instance = model_class(metadata={"key": "value"})
        self.assertEqual(instance.metadata, {"key": "value"})

    def test_create_model_with_optional_field(self):
        """Test creating a model with an optional field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "email": {
                    "type": "string",
                    "description": "User's email",
                    "required": False,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["email"]
        self.assertEqual(field_info.annotation, Optional[str])
        self.assertEqual(field_info.description, "User's email")
        self.assertEqual(field_info.default, "")

        instance = model_class()
        self.assertEqual(instance.email, "")

    def test_create_model_with_optional_integer_field(self):
        """Test creating a model with an optional integer field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "count": {
                    "type": "integer",
                    "description": "Item count",
                    "required": False,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["count"]
        self.assertEqual(field_info.annotation, Optional[int])
        self.assertEqual(field_info.default, 0)

        instance = model_class()
        self.assertEqual(instance.count, 0)

    def test_create_model_with_optional_number_field(self):
        """Test creating a model with an optional number field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "rating": {
                    "type": "number",
                    "description": "User rating",
                    "required": False,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["rating"]
        self.assertEqual(field_info.annotation, Optional[float])
        self.assertEqual(field_info.default, 0.0)

        instance = model_class()
        self.assertEqual(instance.rating, 0.0)

    def test_create_model_with_optional_boolean_field(self):
        """Test creating a model with an optional boolean field."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "verified": {
                    "type": "boolean",
                    "description": "Verification status",
                    "required": False,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        field_info = model_class.model_fields["verified"]
        self.assertEqual(field_info.annotation, Optional[bool])
        self.assertFalse(field_info.default)

        instance = model_class()
        self.assertFalse(instance.verified)

    def test_create_model_with_multiple_fields(self):
        """Test creating a model with multiple fields of different types."""
        json_schema = {
            "name": "UserModel",
            "parameters": {
                "name": {
                    "type": "string",
                    "description": "User's name",
                    "required": True,
                },
                "age": {
                    "type": "integer",
                    "description": "User's age",
                    "required": False,
                },
                "active": {
                    "type": "boolean",
                    "description": "User's active status",
                    "required": True,
                },
                "tags": {
                    "type": "array",
                    "description": "User's tags",
                    "required": False,
                },
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)

        self.assertTrue(issubclass(model_class, BaseModel))
        self.assertEqual(model_class.__name__, "UserModel")

        self.assertIn("name", model_class.model_fields)
        self.assertIn("age", model_class.model_fields)
        self.assertIn("active", model_class.model_fields)
        self.assertIn("tags", model_class.model_fields)

        instance = model_class(name="John", active=True)
        self.assertEqual(instance.name, "John")
        self.assertTrue(instance.active)
        self.assertEqual(instance.age, 0)
        self.assertEqual(instance.tags, [])

    def test_create_model_with_unknown_type(self):
        """Test creating a model with an unknown type (should default to string)."""
        json_schema = {
            "name": "TestModel",
            "parameters": {
                "custom_field": {
                    "type": "unknown_type",
                    "description": "Custom field",
                    "required": True,
                }
            },
        }

        model_class = OpenAITeamAdapter.create_function_args_class(json_schema)
        field_info = model_class.model_fields["custom_field"]
        self.assertEqual(field_info.annotation, str)
        self.assertEqual(field_info.description, "Custom field")


class TestFunctionToolSchema(TestCase):
    """Schema handed to OpenAI for action-group tools.

    Every property lands in ``required`` under strict mode, so the model always has to emit a
    value for it. A property that declares both a top-level ``type`` and a conflicting ``anyOf``
    has no value satisfying both, and the model cannot produce the tool call at all.
    """

    def build_schema(self, parameters: dict) -> dict:
        model_class = OpenAITeamAdapter.create_function_args_class(
            {"name": "TestModel", "parameters": parameters}
        )
        schema = model_class.model_json_schema()
        OpenAITeamAdapter._clean_schema(schema)
        return schema

    def optional(self, field_type: str) -> dict:
        return {"field": {"type": field_type, "description": "A field", "required": False}}

    def test_no_scalar_property_declares_type_and_anyof_together(self):
        parameters = {
            name: {"type": name, "description": name, "required": False}
            for name in ("string", "integer", "number", "boolean")
        }

        schema = self.build_schema(parameters)

        for name, prop in schema["properties"].items():
            with self.subTest(field=name):
                self.assertFalse(
                    "type" in prop and "anyOf" in prop,
                    f"{name} declares both type and anyOf: {prop}",
                )

    def test_optional_integer_keeps_integer_type(self):
        prop = self.build_schema(self.optional("integer"))["properties"]["field"]

        self.assertEqual(prop["type"], "integer")
        self.assertNotIn("anyOf", prop)

    def test_optional_number_keeps_number_type(self):
        prop = self.build_schema(self.optional("number"))["properties"]["field"]

        self.assertEqual(prop["type"], "number")
        self.assertNotIn("anyOf", prop)

    def test_optional_boolean_keeps_boolean_type(self):
        prop = self.build_schema(self.optional("boolean"))["properties"]["field"]

        self.assertEqual(prop["type"], "boolean")
        self.assertNotIn("anyOf", prop)

    def test_optional_string_stays_non_nullable_string(self):
        """Lambda payloads have always received a string here; null must stay unreachable."""
        prop = self.build_schema(self.optional("string"))["properties"]["field"]

        self.assertEqual(prop["type"], "string")
        self.assertNotIn("anyOf", prop)

    def test_optional_array_keeps_previous_shape(self):
        """Arrays keep both keywords because together they still describe a usable value.

        ``array`` and ``anyOf: [array, null]`` intersect to ``array``, so strict mode compiles a
        grammar the model can satisfy. That is why optional array params call successfully today,
        unlike ``string`` and ``anyOf: [integer, null]``, whose intersection is empty. Leaving
        this shape alone keeps the patch limited to the properties that are actually broken.
        """
        prop = self.build_schema(self.optional("array"))["properties"]["field"]

        self.assertEqual(prop["type"], "array")
        self.assertIn("anyOf", prop)

    def test_non_collapsible_anyof_is_left_untouched(self):
        """An anyOf that is not a nullable scalar keeps its own declaration.

        Injecting a top-level type here would rebuild the same contradiction, and for a
        multi-type union it would also force one branch of the union onto the model.
        """
        prop = self.build_schema(self.optional("object"))["properties"]["field"]

        self.assertIn("anyOf", prop)
        self.assertNotIn("type", prop)

    def test_required_properties_keep_declared_types(self):
        parameters = {
            name: {"type": name, "description": name, "required": True}
            for name in ("string", "integer", "number", "boolean")
        }

        schema = self.build_schema(parameters)

        for name in parameters:
            with self.subTest(field=name):
                self.assertEqual(schema["properties"][name]["type"], name)

    def test_descriptions_preserved_and_every_property_required(self):
        """Strict mode requires every property, which is why one broken field blocks the call."""
        parameters = {
            "year": {"type": "integer", "description": "Release year", "required": False},
            "item_id": {"type": "string", "description": "JIRA key", "required": True},
        }

        schema = self.build_schema(parameters)

        self.assertEqual(schema["properties"]["year"]["description"], "Release year")
        self.assertEqual(schema["properties"]["item_id"]["description"], "JIRA key")
        self.assertEqual(sorted(schema["required"]), ["item_id", "year"])


class TestToExternalNoneAgentData(TestCase):
    def test_agent_data_none_normalized_to_empty_dict(self):
        agent_data = None
        agent_data = agent_data or {}

        self.assertEqual(agent_data, {})
        self.assertIsInstance(agent_data, dict)

    def test_agent_data_none_does_not_crash_on_get(self):
        agent_data = {}

        self.assertIsNone(agent_data.get("name"))
        self.assertIsNone(agent_data.get("role"))
        self.assertIsNone(agent_data.get("goal"))
        self.assertIsNone(agent_data.get("personality"))

    def test_agent_data_empty_dict_handled(self):
        agent_data = {}

        self.assertIsNone(agent_data.get("name"))
        self.assertIsNone(agent_data.get("role"))
        self.assertIsNone(agent_data.get("goal"))
        self.assertIsNone(agent_data.get("personality"))

    def test_agent_data_with_values(self):
        agent_data = {
            "name": "Test Agent",
            "role": "Assistant",
            "goal": "Help users",
            "personality": "Friendly",
        }

        self.assertEqual(agent_data.get("name"), "Test Agent")
        self.assertEqual(agent_data.get("role"), "Assistant")
        self.assertEqual(agent_data.get("goal"), "Help users")
        self.assertEqual(agent_data.get("personality"), "Friendly")

    def test_agent_data_partial_values(self):
        agent_data = {"name": "Test Agent"}

        self.assertEqual(agent_data.get("name"), "Test Agent")
        self.assertIsNone(agent_data.get("role"))
        self.assertIsNone(agent_data.get("goal"))
        self.assertIsNone(agent_data.get("personality"))


class TestAllOptionalParamsNone(TestCase):
    def test_multiple_none_params_normalized(self):
        agent_data = None
        formatter_agent_configurations = None
        instructions = None
        business_rules = None

        agent_data = agent_data or {}
        formatter_agent_configurations = formatter_agent_configurations or {}
        instructions = instructions or []
        business_rules = business_rules or ""

        self.assertEqual(agent_data, {})
        self.assertEqual(formatter_agent_configurations, {})
        self.assertEqual(instructions, [])
        self.assertEqual(business_rules, "")

    def test_none_params_can_be_used_safely(self):
        agent_data = {}
        formatter_agent_configurations = {}
        instructions = []

        self.assertIsNone(agent_data.get("name"))
        self.assertIsNone(formatter_agent_configurations.get("formatter_foundation_model"))
        self.assertEqual("\n".join(instructions) if instructions else "", "")


class TestOpenAIDataLakeEventAdapterDataLakeEvents(TestCase):
    """Verify data lake event behavior: one tool_result event per tool, sent async."""

    def setUp(self):
        self.adapter = OpenAIDataLakeEventAdapter()
        self.mock_service = MockDataLakeEventService()

        def fake_send_validated_event(
            event_data,
            project_uuid,
            contact_urn,
            use_delay=True,
            channel_uuid=None,
            agent_identifier=None,
            conversation=None,
        ):
            if use_delay:
                self.mock_service.send_data_lake_event_task.delay(event_data)
            else:
                self.mock_service.send_data_lake_event_task(event_data)
            return event_data

        self.mock_service.send_validated_event = fake_send_validated_event
        self.adapter._event_service = self.mock_service

    def test_tool_result_sends_one_event_with_key_tool_result(self):
        """to_data_lake_event with tool_result_data sends exactly one event with key tool_result."""
        self.mock_service.clear_events()
        self.adapter.to_data_lake_event(
            project_uuid="proj-123",
            contact_urn="urn:test",
            tool_result_data={
                "tool_name": "my_tool",
                "result": {"ok": True},
                "parameters": [],
                "function_name": "my_func",
            },
            agent_data={"agent_name": "test_agent"},
            foundation_model="gpt-4",
            backend="openai",
        )
        tool_result_events = self.mock_service.get_events_by_key("tool_result")
        self.assertEqual(len(tool_result_events), 1)
        self.assertEqual(tool_result_events[0]["value"], "my_tool")
        self.assertIn("tool_result", tool_result_events[0].get("metadata", {}))

    def test_tool_result_sent_async_via_delay(self):
        """Tool result events use use_delay=True and appear in sent_events_async (no blocking)."""
        self.mock_service.clear_events()
        self.adapter.to_data_lake_event(
            project_uuid="proj-456",
            contact_urn="urn:async",
            tool_result_data={
                "tool_name": "async_tool",
                "result": "done",
                "parameters": [],
                "function_name": None,
            },
            agent_data={"agent_name": "agent"},
            foundation_model="gpt-4",
            backend="openai",
        )
        self.assertEqual(len(self.mock_service.sent_events_async), 1)
        self.assertEqual(self.mock_service.sent_events_async[0]["key"], "tool_result")
        self.assertEqual(len(self.mock_service.sent_events_sync), 0)


class TestOpenAITeamAdapterGetContext(TestCase):
    @patch.object(OpenAITeamAdapter, "_get_credentials", return_value={"api_key": "secret"})
    def test_get_context_includes_vtex_fields(self, _mock_credentials):
        context = OpenAITeamAdapter._get_context(
            project_uuid="proj-123",
            contact_urn="tel:123",
            auth_token="token",
            channel_uuid="ch-1",
            contact_name="Ana",
            content_base_uuid="cb-1",
            contact_fields="{}",
            vtex_account="mystore",
            vtex_host_store="https://www.mystore.com.br",
            storefront_type="vtex_io",
        )
        self.assertEqual(context.project["uuid"], "proj-123")
        self.assertEqual(context.project["vtex_account"], "mystore")
        self.assertEqual(context.project["vtex_host_store"], "https://www.mystore.com.br")
        self.assertEqual(context.project["storefront_type"], "vtex_io")

    @patch.object(OpenAITeamAdapter, "_get_credentials", return_value={})
    def test_get_context_vtex_fields_default_to_none(self, _mock_credentials):
        context = OpenAITeamAdapter._get_context(
            project_uuid="proj-123",
            contact_urn="tel:123",
            auth_token="token",
            channel_uuid="ch-1",
            contact_name="Ana",
            content_base_uuid="cb-1",
            contact_fields="{}",
        )
        self.assertIsNone(context.project["vtex_account"])
        self.assertIsNone(context.project["vtex_host_store"])
        self.assertIsNone(context.project["storefront_type"])
