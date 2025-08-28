import json
from typing import Callable, Optional

import boto3
import pendulum
from agents import Agent, FunctionTool, RunContextWrapper, Runner, function_tool, Session
from django.conf import settings
from pydantic import BaseModel, Field, create_model

from inline_agents.adapter import TeamAdapter
from inline_agents.backends.openai.entities import Context
from inline_agents.backends.openai.hooks import HooksDefault
from inline_agents.backends.openai.tools import Supervisor as SupervisorAgent
from nexus.inline_agents.models import AgentCredential, InlineAgentsConfiguration
from nexus.intelligences.models import ContentBase
from nexus.projects.models import Project
from inline_agents.backends.openai.sessions import only_turns, get_watermark, set_watermark


def make_agent_proxy_tool(
    agent: Agent[Context],
    tool_name: str,
    tool_description: str,
    session_factory: Callable
):
    @function_tool
    async def _proxy(ctx: RunContextWrapper[Context], question: str) -> str:
        supervisor_session = ctx.context.session
        agent_session = session_factory(agent.name)

        supervisor_items = await supervisor_session.get_items()
        supervisor_turns = await only_turns(supervisor_items)

        # TODO: get default value using project and contact_urn from ctx.context
        namespace = getattr(supervisor_session, "key",)
        cursor = await get_watermark(agent_session, namespace)

        delta = supervisor_turns[cursor:]
        if delta:
            await agent_session.add_items(delta)
            await set_watermark(agent_session, namespace, len(supervisor_turns))

        result = await Runner.run(
            starting_agent=agent,
            input=question,
            context=ctx.context,
            session=agent_session,
        )
        return result.final_output

    _proxy.name = tool_name
    _proxy.description = tool_description
    return _proxy


class OpenAITeamAdapter(TeamAdapter):
    @classmethod
    def to_external(
        cls,
        supervisor: dict,
        agents: list[dict],
        input_text: str,
        project_uuid: str,
        contact_fields: str,
        contact_urn: str,
        contact_name: str,
        channel_uuid: str,
        hooks: HooksDefault,
        content_base: ContentBase,
        project: Project,
        auth_token: str = "",
        inline_agent_configuration: InlineAgentsConfiguration | None = None,
        session_factory: Callable = None,
        session: Session = None,
        **kwargs
    ) -> list[dict]:
        agents_as_tools = []

        content_base_uuid = str(content_base.uuid)
        business_rules = project.human_support_prompt

        instructions = content_base.instructions.all()
        agent_data = content_base.agent

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
            content_base_uuid=content_base_uuid,
        )

        for agent in agents:
            agent_instructions = agent.get("instruction")

            if isinstance(inline_agent_configuration, InlineAgentsConfiguration):
                default_instructions_for_collaborators = inline_agent_configuration.default_instructions_for_collaborators
                agent_instructions += f"\n{default_instructions_for_collaborators}"

            agent_name = agent.get("agentName")
            if "_agent" not in agent_name:
                agent_name = f"{agent_name}_agent"
            openai_agent = Agent[Context](
                name=agent_name,
                instructions=agent_instructions,
                tools=cls._get_tools(agent["actionGroups"]),
                model=settings.OPENAI_AGENTS_FOUNDATION_MODEL,
                hooks=hooks
            )
            agents_as_tools.append(
                make_agent_proxy_tool(
                    agent=openai_agent,
                    tool_name=agent.get("agentName"),
                    tool_description=agent.get("collaborator_configurations"),
                    session_factory=session_factory
                )
            )

        supervisor_tools = cls._get_tools(supervisor["tools"])
        supervisor_tools.extend(agents_as_tools)

        supervisor_agent = SupervisorAgent(
            name="manager",
            instructions=instruction,
            tools=supervisor_tools,
            hooks=hooks,
            model=supervisor["foundation_model"],
            prompt_override_configuration=supervisor.get("prompt_override_configuration", {})
        )
        return {
            "starting_agent": supervisor_agent,
            "input": input_text,
            "context": cls._get_context(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                auth_token=auth_token,
                channel_uuid=channel_uuid,
                contact_name=contact_name,
                content_base_uuid=content_base_uuid,
                session=session,
                input_text=input_text,
            )
        }

    @classmethod
    def _get_context(
        cls,
        project_uuid: str,
        contact_urn: str,
        auth_token: str,
        channel_uuid: str,
        contact_name: str,
        content_base_uuid: str,
        globals_dict: dict = {},
        session: Session = None,
        input_text: str = "",
    ) -> Context:
        credentials = cls._get_credentials(project_uuid)
        contact = {"urn": contact_urn, "channel_uuid": channel_uuid, "name": contact_name}
        project = {"uuid": project_uuid, "auth_token": auth_token}
        content_base = {"uuid": content_base_uuid}

        return Context(
            credentials=credentials,
            globals=globals_dict,
            contact=contact,
            project=project,
            content_base=content_base,
            session=session,
            input_text=input_text,
        )

    @classmethod
    def _get_credentials(cls, project_uuid: str) -> dict:
        agent_credentials = AgentCredential.objects.filter(project_id=project_uuid)
        credentials = {}
        for credential in agent_credentials:
            credentials[credential.key] = credential.decrypted_value
        return credentials

    @classmethod
    def _get_tools(cls, action_groups: list[dict]) -> list[dict]:
        tools = []
        for action_group in action_groups:
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

    def invoke_aws_lambda(
        cls,
        function_name: str,
        function_arn: str,
        payload: dict,
        credentials: dict,
        globals: dict,
        contact: dict,
        project: dict,
    ) -> str:
        try:
            lambda_client = boto3.client("lambda", region_name="us-east-1")
            parameters = []
            for key, value in payload.items():
                parameters.append({
                    "name": key,
                    "value": value
                })

            session_attributes = {
                "credentials": json.dumps(credentials),
                "globals": json.dumps(globals),
                "contact": json.dumps(contact),
                "project": json.dumps(project)
            }

            payload_json = {
                "parameters": parameters,
                "sessionAttributes": session_attributes,
                "promptSessionAttributes": {"alwaysFormat": "<example>{'msg': {'text': 'Hello, how can I help you today?'}}</example>"},
                "agent": {
                    "name": "INLINE_AGENT",
                    "version": "INLINE_AGENT",
                    "id": "INLINE_AGENT",
                },
                "actionGroup": function_name,
                "function": function_arn,
                "messageVersion": "1.0",
            }

            payload_json = json.dumps(payload_json)

            response = lambda_client.invoke(
                FunctionName=function_arn,
                InvocationType='RequestResponse',
                Payload=payload_json
            )
            lambda_result = response['Payload'].read().decode('utf-8')
            result = json.loads(lambda_result)

            if 'FunctionError' in response:
                error_details = json.loads(lambda_result)
                print(f"FunctionError on lambda '{function_name}': {error_details}")
                return json.dumps({
                    "error": f"FunctionError on lambda: {error_details.get('errorMessage', 'Unknown error')}"
                })

            return result["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
        except Exception as e:
            print(f"Error on lambda '{function_name}': {e}")
            return json.dumps({"error": f"Error on lambda: {str(e)}"})

    @classmethod
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

            default_value = {
                "string": "",
                "integer": 0,
                "number": 0.0,
                "boolean": False,
                "array": [],
                "object": {}
            }.get(field_type, str)

            if required:
                fields[field_name] = (python_type, Field(description=description))
            else:
                fields[field_name] = (Optional[python_type], Field(description=description, default=default_value))

        model_name = json_schema.get("name", "DynamicFunctionArgs")
        return create_model(model_name, **fields)

    def create_function_tool(cls, function_name: str, function_arn: str, function_description: str, json_schema: dict) -> FunctionTool:
        async def invoke_specific_lambda(ctx: RunContextWrapper[Context], args: str) -> str:
            parsed = tool_function_args.model_validate_json(args)
            payload = parsed.model_dump()
            return cls.invoke_aws_lambda(
                cls,
                function_name=function_name,
                function_arn=function_arn,
                payload=payload,
                credentials=ctx.context.credentials,
                globals=ctx.context.globals,
                contact=ctx.context.contact,
                project=ctx.context.project
            )

        tool_function_args = cls.create_function_args_class(json_schema)
        payload_schema = tool_function_args.model_json_schema()

        cls._clean_schema(payload_schema)
        payload_schema.update({"additionalProperties": False})

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


def create_standardized_event(agent_name, type, tool_name="", original_trace=None):
    return {
        "type": "trace_update",
        "trace": {
            "config": {
                "agentName": agent_name,
                "toolName": tool_name,
                "type": type,
            },
            "trace": original_trace if original_trace is not None else {}
        }
    }


def process_openai_trace(event):
    standardized_event = {}

    event_type = event.get("event_type")

    if event_type != "run_item_stream_event":
        return []

    agent_name = event.get("agent_name", "Unknown")
    item = event.get("event_data", {}).get("item", {})
    item_type = item.get("type")

    simplified_event_data = {
        "type": event["event_data"]["type"],
        "item": {"type": item_type}
    }
    original_trace = {
        "timestamp": event["timestamp"],
        "event_type": event["event_type"],
        "event_data": simplified_event_data,
        "agent_name": agent_name
    }

    if item_type == "reasoning_item":
        standardized_event = create_standardized_event(agent_name, "thinking", original_trace=original_trace)
    elif item_type == "tool_call_item":
        tool_name = item.get("raw_item", {}).get("name", "")
        event_class = "delegating_to_agent" if "agent" in tool_name else "executing_tool"
        original_trace["event_data"]["item"]["raw_item"] = {"arguments": item["raw_item"]["arguments"], "name": tool_name, "type": item["raw_item"]["type"]}
        standardized_event = create_standardized_event(tool_name, event_class, tool_name, original_trace)
    elif item_type == "tool_call_output_item":
        original_trace["event_data"]["item"]["output"] = item["output"]
        standardized_event = create_standardized_event(agent_name, "tool_result_received", "", original_trace)
    elif item_type == "message_output_item":
        original_trace["event_data"]["item"]["raw_item"] = {"content": item["raw_item"]["content"], "role": item["raw_item"]["role"], "status": item["raw_item"]["status"], "type": item["raw_item"]["type"]}
        standardized_event = create_standardized_event(agent_name, "sending_response", original_trace=original_trace)
    return standardized_event
