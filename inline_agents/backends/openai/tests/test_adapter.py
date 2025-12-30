from typing import Optional

from django.test import TestCase
from pydantic import BaseModel, ValidationError

from inline_agents.backends.openai.adapter import OpenAITeamAdapter


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
