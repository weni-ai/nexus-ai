import json
from typing import Any

import boto3
import pendulum
from agents import Agent, FunctionTool, RunContextWrapper
from pydantic import BaseModel, Field, create_model

from inline_agents.adapter import TeamAdapter
from inline_agents.backends.openai.tools import search_in_knowledge_base


class OpenAITeamAdapter(TeamAdapter):
    @classmethod
    def to_external(cls, supervisor: dict, agents: list[dict], input_text: str, project_uuid: str, contact_fields: str, contact_urn: str, contact_name: str, channel_uuid: str) -> list[dict]:
        handoffs = []
        print("AGENTS", agents)

        from nexus.projects.models import Project
        from nexus.usecases.intelligences.get_by_uuid import (
            get_default_content_base_by_project,
        )
        content_base = get_default_content_base_by_project(project_uuid)
        instructions = content_base.instructions.all()
        agent_data = content_base.agent

        project = Project.objects.get(uuid=project_uuid)
        business_rules = project.human_support_prompt
        supervisor_instructions = list(instructions.values_list("instruction", flat=True))
        supervisor_instructions = "\n".join(supervisor_instructions)

        time_now = pendulum.now("America/Sao_Paulo")
        llm_formatted_time = f"Today is {time_now.format('dddd, MMMM D, YYYY [at] HH:mm:ss z')}"

        instruction = cls._format_supervisor_instructions(
            instruction=supervisor["instruction"],
            date_time_now=llm_formatted_time,
            contact_fields=contact_fields,
            supervisor_name=agent_data.name,
            supervisor_role=agent_data.role,
            supervisor_goal=agent_data.goal,
            supervisor_adjective=agent_data.personality,
            supervisor_instructions=supervisor_instructions if supervisor_instructions else "",
            business_rules=business_rules if business_rules else "",
            project_id=project_uuid,
            contact_id=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            content_base_uuid=str(content_base.uuid),
        )

        for agent in agents:
            openai_agent = Agent(
                name=agent.get("agentName"),
                instructions=instruction,
                tools=cls._get_tools(agent["actionGroups"]),
                model=agent.get("foundationModel"),
                handoff_description=agent.get("collaborator_configurations", f"Specialist in {agent.get('agentName', 'specific subjects')}")
            )
            handoffs.append(openai_agent)

        supervisor_agent = Agent(
            name="Supervisor Agent",
            instructions=supervisor.get("instruction"),
            handoffs=handoffs,
            tools=cls._get_supervisor_tools(supervisor["tools"])
        )
        return {
            "starting_agent": supervisor_agent,
            "input": input_text
        }

    @classmethod
    def _get_tools(cls, action_groups: list[dict]) -> list[dict]:
        tools = []
        for action_group in action_groups:
            print(f"[DEBUG] Action group: {action_group}")
            group_executor = action_group.get("actionGroupExecutor")
            if not group_executor:
                continue
            tool = cls.create_function_tool(
                cls=cls,
                function_name=action_group.get("actionGroupName"),
                function_arn=group_executor.get("lambda"),
                function_description=action_group.get("actionGroupDescription"),
                json_schema=action_group.get("functionSchema", {}).get("functions", [{}])[0]
            )
            tools.append(tool)

        return tools

    @classmethod
    def _get_supervisor_tools(cls, tools: list[dict]) -> list:
        supervisor_tools = cls._get_tools(tools)
        supervisor_tools.append(search_in_knowledge_base)
        return supervisor_tools

    def invoke_aws_lambda(cls, function_name: str, function_arn: str, payload: dict) -> str:
        try:
            lambda_client = boto3.client("lambda", region_name="us-east-1")
            parameters = []
            for key, value in payload.items():
                parameters.append({
                    "name": key,
                    "value": value
                })
            payload_json = json.dumps({"parameters": parameters})
            response = lambda_client.invoke(
                FunctionName=function_arn,
                InvocationType='RequestResponse',
                Payload=payload_json
            )
            lambda_result = response['Payload'].read().decode('utf-8')

            if 'FunctionError' in response:
                error_details = json.loads(lambda_result)
                print(f"Error on lambda '{function_name}': {error_details}")
                return json.dumps({
                    "error": f"Error on lambda: {error_details.get('errorMessage', 'Unknown error')}"
                })

            return lambda_result
        except Exception as e:
            print(f"Error on lambda '{function_name}': {e}")
            return json.dumps({"error": f"Error on lambda: {str(e)}"})

    def create_function_args_class(cls, json_schema: dict) -> type[BaseModel]:
        parameters = json_schema.get("parameters", {})
        fields = {}
        for field_name, field_config in parameters.items():
            field_type = field_config.get("type", "string")
            description = field_config.get("description", "")
            required = field_config.get("required", False)
            python_type = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict
            }.get(field_type, str)

            if required:
                fields[field_name] = (python_type, Field(description=description))
            else:
                from typing import Optional
                fields[field_name] = (Optional[python_type], Field(description=description, default=None))

        model_name = json_schema.get("name", "DynamicFunctionArgs")
        return create_model(model_name, **fields)

    def create_function_tool(cls, function_name: str, function_arn: str, function_description: str, json_schema: dict) -> FunctionTool:
        async def invoke_specific_lambda(ctx: RunContextWrapper[Any], args: str) -> str:
            parsed = tool_function_args.model_validate_json(args)
            payload = parsed.model_dump()
            return cls.invoke_aws_lambda(cls, function_name=function_name, function_arn=function_arn, payload=payload)

        tool_function_args = cls.create_function_args_class(cls, json_schema)
        payload_schema = tool_function_args.model_json_schema()
        
        print(f"[DEBUG] Original schema for {function_name}: {payload_schema}")

        cls._clean_schema(payload_schema)
        payload_schema.update({"additionalProperties": False})
        
        print(f"[DEBUG] Cleaned schema for {function_name}: {payload_schema}")

        return FunctionTool(
            name=function_name,
            description=function_description,
            params_json_schema=payload_schema,
            on_invoke_tool=invoke_specific_lambda
        )

    @classmethod
    def _clean_schema(cls, schema: dict):
        """Clean up the schema to ensure it's valid for OpenAI"""
        if isinstance(schema, dict):
            if "properties" in schema:
                for prop_name, prop_schema in schema["properties"].items():
                    if isinstance(prop_schema, dict) and "type" not in prop_schema:
                        if "items" in prop_schema:
                            prop_schema["type"] = "array"
                        else:
                            prop_schema["type"] = "string"
                    
                    cls._clean_schema(prop_schema)
            
            if "items" in schema:
                if not schema["items"] or ("type" not in schema["items"] and isinstance(schema["items"], dict)):
                    schema["items"] = {"type": "string"}
                cls._clean_schema(schema["items"])
            
            if "properties" in schema and "required" in schema:
                schema["required"] = list(schema["properties"].keys())
                print(f"[DEBUG] Set all properties as required: {schema['required']}")

    @classmethod
    def _format_supervisor_instructions(
        cls,
        instruction: str,
        date_time_now: str,
        contact_fields: str,
        supervisor_name: str,
        supervisor_role: str,
        supervisor_goal: str,
        supervisor_adjective: str,
        supervisor_instructions: str,
        business_rules: str,
        project_id: str,
        contact_id: str,
        contact_name: str = "",
        channel_uuid: str = "",
        content_base_uuid: str = ""
    ) -> str:

        instruction = instruction or ""
        date_time_now = date_time_now or ""
        contact_fields = contact_fields or ""
        supervisor_name = supervisor_name or ""
        supervisor_role = supervisor_role or ""
        supervisor_goal = supervisor_goal or ""
        supervisor_adjective = supervisor_adjective or ""
        supervisor_instructions = supervisor_instructions or ""
        business_rules = business_rules or ""
        project_id = str(project_id) if project_id else ""
        contact_id = str(contact_id) if contact_id else ""

        instruction = instruction.replace(
            "{{DATE_TIME_NOW}}", date_time_now
        ).replace(
            "{{CONTACT_FIELDS}}", contact_fields
        ).replace(
            "{{SUPERVISOR_NAME}}", supervisor_name
        ).replace(
            "{{SUPERVISOR_ROLE}}", supervisor_role
        ).replace(
            "{{SUPERVISOR_GOAL}}", supervisor_goal
        ).replace(
            "{{SUPERVISOR_ADJECTIVE}}", supervisor_adjective
        ).replace(
            "{{SUPERVISOR_INSTRUCTIONS}}", supervisor_instructions
        ).replace(
            "{{BUSINESS_RULES}}", business_rules
        ).replace(
            "{{PROJECT_ID}}", project_id
        ).replace(
            "{{CONTACT_ID}}", contact_id
        ).replace(
            "{{CONTACT_NAME}}", contact_name
        ).replace(
            "{{CHANNEL_UUID}}", channel_uuid
        ).replace(
            "{{CONTENT_BASE_UUID}}", content_base_uuid
        )
        return instruction