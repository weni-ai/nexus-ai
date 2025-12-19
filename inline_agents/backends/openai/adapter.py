import json
import logging
from typing import Any, Callable, Optional

import boto3
import pendulum
import sentry_sdk
from django.conf import settings
from django.template import Context as TemplateContext
from django.template import Template
from pydantic import BaseModel, Field, create_model

from inline_agents.adapter import DataLakeEventAdapter, TeamAdapter
from inline_agents.backends.data_lake import send_data_lake_event
from inline_agents.backends.openai.entities import Context, HooksState
from inline_agents.backends.openai.event_extractor import OpenAIEventExtractor
from inline_agents.backends.openai.hooks import (
    CollaboratorHooks,
    RunnerHooks,
    SupervisorHooks,
)
from inline_agents.data_lake.event_service import DataLakeEventService
from nexus.inline_agents.models import (
    AgentCredential,
    Guardrail,
    InlineAgentsConfiguration,
)

logger = logging.getLogger(__name__)


def make_agent_proxy_tool(agent, tool_name: str, tool_description: str, session_factory: Callable):
    from agents import RunContextWrapper, Runner, function_tool

    from inline_agents.backends.openai.sessions import get_watermark, only_turns, set_watermark

    @function_tool
    async def _proxy(ctx: RunContextWrapper[Context], question: str) -> str:
        """
        Args:
            question: Plain-text instruction for the agent in "Agent Name", aligned with
            "Agent Collaboration Instructions", stating goal, key context, constraints, and desired output.
        """
        supervisor_session = ctx.context.session
        agent_session = session_factory(agent.name)

        supervisor_items = await supervisor_session.get_items()
        supervisor_turns = await only_turns(supervisor_items)

        namespace = supervisor_session.get_session_id()

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
    _proxy.params_json_schema["properties"]["question"]["description"] = (
        'Plain-text instruction for the agent in "Agent Name", aligned with '
        '"Agent Collaboration Instructions", stating goal, key context, constraints, and desired output.'
    )
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
        supervisor_hooks: SupervisorHooks,
        runner_hooks: RunnerHooks,
        auth_token: str = "",
        inline_agent_configuration: InlineAgentsConfiguration | None = None,
        # Cached inline agent config data (optional, used to avoid database queries)
        default_instructions_for_collaborators: str = None,
        session_factory: Callable = None,
        session: Any = None,
        data_lake_event_adapter: DataLakeEventAdapter = None,
        preview: bool = False,
        hooks_state: HooksState = None,
        event_manager_notify: callable = None,
        rationale_switch: bool = False,
        language: str = "en",
        user_email: str = None,
        session_id: str = None,
        msg_external_id: str = None,
        turn_off_rationale: bool = False,
        use_components: bool = False,
        # Cached data parameters (optional, used to avoid database queries)
        content_base_uuid: str = None,
        business_rules: str = None,
        instructions: list[str] = None,
        agent_data: dict = None,
        **kwargs,
    ) -> list[dict]:
        agents_as_tools = []

        # Cached data is always provided from start_inline_agents
        if content_base_uuid is None:
            raise ValueError("content_base_uuid must be provided")

        # business_rules, instructions, and agent_data can be None if not configured
        # but they are always provided from cache (may be None if not set in project/content_base)

        supervisor_instructions = "\n".join(instructions) if instructions else ""

        time_now = pendulum.now("America/Sao_Paulo")
        llm_formatted_time = f"Today is {time_now.format('dddd, MMMM D, YYYY [at] HH:mm:ss z')}"

        max_tokens = supervisor.get("max_tokens", 2048)

        # Extract agent data fields (agent_data is a dict from cache)
        agent_name = agent_data.get("name")
        agent_role = agent_data.get("role")
        agent_goal = agent_data.get("goal")
        agent_personality = agent_data.get("personality")

        instruction = cls.get_supervisor_instructions(
            instruction=supervisor["instruction"],
            date_time_now=llm_formatted_time,
            contact_fields=contact_fields,
            supervisor_name=agent_name,
            supervisor_role=agent_role,
            supervisor_goal=agent_goal,
            supervisor_adjective=agent_personality,
            supervisor_instructions=supervisor_instructions if supervisor_instructions else "",
            business_rules=business_rules if business_rules else "",
            project_id=project_uuid,
            contact_id=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            content_base_uuid=content_base_uuid,
            use_components=use_components,
            use_human_support=supervisor.get("use_human_support", False),
            components_instructions=supervisor.get("components_instructions", ""),
            components_instructions_up=supervisor.get("components_instructions_up", ""),
            human_support_instructions=supervisor.get("human_support_instructions", ""),
        )

        for agent in agents:
            agent_instructions = agent.get("instruction")

            if default_instructions_for_collaborators:
                agent_instructions += f"\n{default_instructions_for_collaborators}"

            supervisor_default_collaborator_instructions = supervisor.get("default_instructions_for_collaborators", "")
            if supervisor_default_collaborator_instructions and isinstance(
                supervisor_default_collaborator_instructions, str
            ):
                agent_instructions += f"\n{supervisor_default_collaborator_instructions}"

            agent_name = agent.get("agentName")

            hooks = CollaboratorHooks(
                agent_name=agent_name,
                data_lake_event_adapter=data_lake_event_adapter,
                hooks_state=hooks_state,
                event_manager_notify=event_manager_notify,
                preview=preview,
                rationale_switch=rationale_switch,
                language=language,
                user_email=user_email,
                session_id=session_id,
                msg_external_id=msg_external_id,
                turn_off_rationale=turn_off_rationale,
            )

            from agents import Agent, ModelSettings

            openai_agent = Agent[Context](
                name=agent_name,
                instructions=agent_instructions,
                tools=cls._get_tools(agent["actionGroups"]),
                model=agent.get("foundationModel", settings.OPENAI_AGENTS_FOUNDATION_MODEL),
                hooks=hooks,
                model_settings=ModelSettings(
                    max_tokens=max_tokens,
                ),
            )

            agents_as_tools.append(
                make_agent_proxy_tool(
                    agent=openai_agent,
                    tool_name=agent.get("agentName"),
                    tool_description=(
                        f'Agent Name: {agent.get("agentDisplayName")}\n'
                        f"Agent Collaboration Instructions: {agent.get('collaborator_configurations')}"
                    ),
                    session_factory=session_factory,
                )
            )

        supervisor_tools = cls._get_tools(supervisor["tools"])
        supervisor_tools.extend(agents_as_tools)

        from inline_agents.backends.openai.tools import Supervisor as SupervisorAgent

        supervisor_agent = SupervisorAgent(
            name="manager",
            instructions=instruction,
            tools=supervisor_tools,
            hooks=supervisor_hooks,
            model=supervisor["foundation_model"],
            prompt_override_configuration=supervisor.get("prompt_override_configuration", {}),
            preview=preview,
            max_tokens=max_tokens,
            use_components=use_components,
        )

        supervisor_hooks.set_knowledge_base_tool(supervisor_agent.knowledge_base_bedrock.name)

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
                hooks_state=hooks_state,
                contact_fields=contact_fields,
            ),
            "formatter_agent_instructions": supervisor.get("formatter_agent_components_instructions", ""),
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
        contact_fields: str,
        globals_dict: Optional[dict] = None,
        session: Optional[Any] = None,
        input_text: str = "",
        hooks_state: Optional[HooksState] = None,
    ) -> Context:
        if globals_dict is None:
            globals_dict = {}

        try:
            contact_fields = json.loads(contact_fields)
        except json.JSONDecodeError:
            contact_fields = {}

        credentials = cls._get_credentials(project_uuid)
        contact = {"urn": contact_urn, "channel_uuid": channel_uuid, "name": contact_name, "fields": contact_fields}
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
            hooks_state=hooks_state,
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
                function_description=action_group.get("description"),
                json_schema=action_group.get("functionSchema", {}).get("functions", [{}])[0],
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
        ctx,
    ) -> str:
        try:
            lambda_client = boto3.client("lambda", region_name="us-east-1")
            parameters = []
            for key, value in payload.items():
                parameters.append({"name": key, "value": value})
            # ctx.context.hooks_state.add_tool_call(
            #     {
            #         function_name: parameters
            #     }
            # )

            ctx.context.hooks_state.add_tool_info(function_name, {"parameters": parameters})

            session_attributes = {
                "credentials": json.dumps(credentials),
                "globals": json.dumps(globals),
                "contact": json.dumps(contact),
                "project": json.dumps(project),
            }

            payload_json = {
                "parameters": parameters,
                "sessionAttributes": session_attributes,
                "promptSessionAttributes": {
                    "alwaysFormat": "<example>{'msg': {'text': 'Hello, how can I help you today?'}}</example>"
                },
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
                FunctionName=function_arn, InvocationType="RequestResponse", Payload=payload_json
            )
            lambda_result = response["Payload"].read().decode("utf-8")
            result = json.loads(lambda_result)

            if "FunctionError" in response:
                error_details = json.loads(lambda_result)
                logger.error(
                    f"FunctionError on lambda '{function_name}': {error_details}. "
                    f"Contact: {contact.get('urn', 'unknown')}, "
                    f"Project: {project.get('uuid', 'unknown')}"
                )
                return json.dumps(
                    {"error": f"FunctionError on lambda: {error_details.get('errorMessage', 'Unknown error')}"}
                )

            session_attributes = result.get("response", {}).get("sessionAttributes", {})

            events = []
            if isinstance(session_attributes, dict):
                events = session_attributes.get("events", [])
            elif isinstance(session_attributes, str):
                try:
                    session_attrs_parsed = json.loads(session_attributes)
                    events = session_attrs_parsed.get("events", [])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Fallback: check top-level response for events
            if not events:
                events = result.get("response", {}).get("events", [])

            if not events:
                logger.warning(
                    f"No events returned by Lambda '{function_name}'. "
                    f"This may indicate that the record will not be created in contact history. "
                    f"Contact: {contact.get('urn', 'unknown')}, "
                    f"Project: {project.get('uuid', 'unknown')}"
                )
                sentry_sdk.set_context(
                    "missing_lambda_events",
                    {
                        "function_name": function_name,
                        "contact_urn": contact.get("urn", "unknown"),
                        "project_uuid": project.get("uuid", "unknown"),
                        "response_keys": list(result.get("response", {}).keys())
                        if isinstance(result.get("response"), dict)
                        else [],
                    },
                )
                sentry_sdk.capture_message(f"Lambda '{function_name}' did not return events", level="warning")
            else:
                logger.info(
                    f"Lambda '{function_name}' returned {len(events)} event(s). "
                    f"Contact: {contact.get('urn', 'unknown')}"
                )

            ctx.context.hooks_state.add_tool_info(function_name, session_attributes)

            return result["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]
        except Exception as e:
            logger.error(
                f"Error on lambda '{function_name}': {e}. "
                f"Contact: {contact.get('urn', 'unknown')}, "
                f"Project: {project.get('uuid', 'unknown')}"
            )
            sentry_sdk.set_context(
                "lambda_invocation_error",
                {
                    "function_name": function_name,
                    "function_arn": function_arn,
                    "contact_urn": contact.get("urn", "unknown"),
                    "project_uuid": project.get("uuid", "unknown"),
                    "error": str(e),
                },
            )
            sentry_sdk.capture_exception(e)
            return json.dumps({"error": f"Error on lambda: {str(e)}"})

    @classmethod
    def create_function_args_class(cls, json_schema: dict) -> type[BaseModel]:
        parameters = json_schema.get("parameters", {})
        fields = {}
        for field_name, field_config in parameters.items():
            field_type = field_config.get("type", "string")

            if "type" not in field_config and cls._is_array_schema(field_config):
                field_type = "array"

            description = field_config.get("description", "")
            required = field_config.get("required", False)
            python_type = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict,
            }.get(field_type, str)

            default_value = {
                "string": "",
                "integer": 0,
                "number": 0.0,
                "boolean": False,
                "array": [],
                "object": {},
            }.get(field_type, str)

            if required:
                fields[field_name] = (python_type, Field(description=description))
            else:
                fields[field_name] = (Optional[python_type], Field(description=description, default=default_value))

        model_name = json_schema.get("name", "DynamicFunctionArgs")
        return create_model(model_name, **fields)

    def create_function_tool(
        cls, function_name: str, function_arn: str, function_description: str, json_schema: dict
    ) -> Any:
        from agents import FunctionTool, RunContextWrapper

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
                project=ctx.context.project,
                ctx=ctx,
            )

        tool_function_args = cls.create_function_args_class(json_schema)
        payload_schema = tool_function_args.model_json_schema()

        cls._clean_schema(payload_schema)
        payload_schema.update({"additionalProperties": False})

        return FunctionTool(
            name=function_name,
            description=function_description,
            params_json_schema=payload_schema,
            on_invoke_tool=invoke_specific_lambda,
        )

    @classmethod
    def _is_array_schema(cls, schema: dict) -> bool:
        """Check if a schema should be treated as an array type"""
        if not isinstance(schema, dict):
            return False

        if schema.get("type") == "array":
            return True

        if "items" in schema:
            return True

        if "anyOf" in schema:
            for option in schema["anyOf"]:
                if isinstance(option, dict) and "items" in option:
                    return True
        if "oneOf" in schema:
            for option in schema["oneOf"]:
                if isinstance(option, dict) and "items" in option:
                    return True

        return False

    @classmethod
    def _clean_schema_list(cls, schema_list: list):
        """Helper to recursively clean a list of schemas (for anyOf/oneOf)"""
        if not isinstance(schema_list, list):
            return

        for option in schema_list:
            if isinstance(option, dict):
                if cls._is_array_schema(option) and "type" not in option:
                    option["type"] = "array"

                if "items" in option and isinstance(option["items"], dict):
                    if "type" not in option["items"]:
                        option["items"]["type"] = "string"

                cls._clean_schema(option)

    @classmethod
    def _fix_property_schema(cls, prop_schema: Any):
        """Helper to fix the type of a single property's schema"""
        if isinstance(prop_schema, dict) and "type" not in prop_schema:
            if cls._is_array_schema(prop_schema):
                prop_schema["type"] = "array"
            else:
                prop_schema["type"] = "string"

        cls._clean_schema(prop_schema)

    @classmethod
    def _clean_schema(cls, schema: dict):
        """
        Clean up the schema recursively to ensure it's valid for OpenAI.
        """
        if not isinstance(schema, dict):
            return

        cls._clean_schema_list(schema.get("anyOf"))
        cls._clean_schema_list(schema.get("oneOf"))

        if "properties" in schema:
            for prop_schema in schema["properties"].values():
                cls._fix_property_schema(prop_schema)

        if "items" in schema:
            items = schema["items"]
            if not items:
                schema["items"] = {"type": "string"}
            elif isinstance(items, dict):
                if "type" not in items:
                    items["type"] = "string"
                cls._clean_schema(items)

        if "properties" in schema and "required" in schema:
            schema["required"] = list(schema["properties"].keys())

    @classmethod
    def get_supervisor_instructions(
        cls,
        instruction,
        date_time_now,
        contact_fields,
        supervisor_name,
        supervisor_role,
        supervisor_goal,
        supervisor_adjective,
        supervisor_instructions,
        business_rules,
        project_id,
        contact_id,
        contact_name,
        channel_uuid,
        content_base_uuid,
        use_components,
        use_human_support,
        components_instructions,
        components_instructions_up,
        human_support_instructions,
    ) -> str:
        general_context_data = {
            "PROJECT_ID": project_id,
            "CONTACT_ID": contact_id,
            "CONTACT_NAME": contact_name,
            "CHANNEL_UUID": channel_uuid,
            "CONTENT_BASE_UUID": content_base_uuid,
            "DATE_TIME_NOW": date_time_now,
            "CONTACT_FIELDS": contact_fields,
            "SUPERVISOR_NAME": supervisor_name,
            "SUPERVISOR_ROLE": supervisor_role,
            "SUPERVISOR_GOAL": supervisor_goal,
            "SUPERVISOR_ADJECTIVE": supervisor_adjective,
            "SUPERVISOR_INSTRUCTIONS": supervisor_instructions,
            "BUSINESS_RULES": business_rules,
        }

        if use_human_support:
            human_support_template = Template(human_support_instructions)
            human_support_context = TemplateContext(general_context_data)
            human_support_instructions = human_support_template.render(human_support_context)

        if use_components:
            components_template = Template(components_instructions)
            components_context = TemplateContext(general_context_data)
            components_instructions = components_template.render(components_context)

            components_template_up = Template(components_instructions_up)
            components_context_up = TemplateContext(general_context_data)
            components_instructions_up = components_template_up.render(components_context_up)

        template_string = instruction
        template = Template(template_string)

        prompt_control_context_data = {
            "USE_HUMAN_SUPPORT": use_human_support,
            "HUMAN_SUPPORT_INSTRUCTIONS": human_support_instructions,
            "USE_COMPONENTS": use_components,
            "COMPONENTS_INSTRUCTIONS": components_instructions,
            "COMPONENTS_INSTRUCTIONS_UP": components_instructions_up,
        }

        context_data = {**general_context_data, **prompt_control_context_data}

        context_object = TemplateContext(context_data)

        rendered_content = template.render(context_object)

        return rendered_content

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
        content_base_uuid: str = "",
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

        instruction = (
            instruction.replace("{{DATE_TIME_NOW}}", date_time_now)
            .replace("{{CONTACT_FIELDS}}", contact_fields)
            .replace("{{SUPERVISOR_NAME}}", supervisor_name)
            .replace("{{SUPERVISOR_ROLE}}", supervisor_role)
            .replace("{{SUPERVISOR_GOAL}}", supervisor_goal)
            .replace("{{SUPERVISOR_ADJECTIVE}}", supervisor_adjective)
            .replace("{{SUPERVISOR_INSTRUCTIONS}}", supervisor_instructions)
            .replace("{{BUSINESS_RULES}}", business_rules)
            .replace("{{PROJECT_ID}}", project_id)
            .replace("{{CONTACT_ID}}", contact_id)
            .replace("{{CONTACT_NAME}}", contact_name)
            .replace("{{CHANNEL_UUID}}", channel_uuid)
            .replace("{{CONTENT_BASE_UUID}}", content_base_uuid)
        )
        return instruction

    @classmethod
    def _get_guardrails(cls, project_uuid: str) -> list[dict]:
        try:
            guardrails = Guardrail.objects.get(project__uuid=project_uuid)
        except Guardrail.DoesNotExist:
            guardrails = Guardrail.objects.filter(current_version=True).order_by("created_on").last()

        return {"guardrailIdentifier": guardrails.identifier, "guardrailVersion": str(guardrails.version)}


def create_standardized_event(agent_name, type, tool_name="", original_trace=None):
    return {
        "type": "trace_update",
        "trace": {
            "config": {
                "agentName": agent_name,
                "toolName": tool_name,
                "type": type,
            },
            "trace": original_trace if original_trace is not None else {},
        },
    }


def process_openai_trace(event):
    standardized_event = {}

    event_type = event.get("event_type")

    if event_type != "run_item_stream_event":
        return []

    agent_name = event.get("agent_name", "Unknown")
    item = event.get("event_data", {}).get("item", {})
    item_type = item.get("type")

    simplified_event_data = {"type": event["event_data"]["type"], "item": {"type": item_type}}
    original_trace = {
        "timestamp": event["timestamp"],
        "event_type": event["event_type"],
        "event_data": simplified_event_data,
        "agent_name": agent_name,
    }

    if item_type == "reasoning_item":
        standardized_event = create_standardized_event(agent_name, "thinking", original_trace=original_trace)
    elif item_type == "tool_call_item":
        tool_name = item.get("raw_item", {}).get("name", "")
        event_class = "delegating_to_agent" if "agent" in tool_name else "executing_tool"
        original_trace["event_data"]["item"]["raw_item"] = {
            "arguments": item["raw_item"]["arguments"],
            "name": tool_name,
            "type": item["raw_item"]["type"],
        }
        standardized_event = create_standardized_event(tool_name, event_class, tool_name, original_trace)
    elif item_type == "tool_call_output_item":
        original_trace["event_data"]["item"]["output"] = item["output"]
        standardized_event = create_standardized_event(agent_name, "tool_result_received", "", original_trace)
    elif item_type == "message_output_item":
        original_trace["event_data"]["item"]["raw_item"] = {
            "content": item["raw_item"]["content"],
            "role": item["raw_item"]["role"],
            "status": item["raw_item"]["status"],
            "type": item["raw_item"]["type"],
        }
        standardized_event = create_standardized_event(agent_name, "sending_response", original_trace=original_trace)
    return standardized_event


class OpenAIDataLakeEventAdapter(DataLakeEventAdapter):
    """Adapter for transforming OpenAI traces to data lake event format."""

    def __init__(self, send_data_lake_event_task: callable = None):
        if send_data_lake_event_task is None:
            send_data_lake_event_task = self._get_send_data_lake_event_task()
        self._event_service = DataLakeEventService(send_data_lake_event_task)

    def _get_send_data_lake_event_task(self) -> callable:
        return send_data_lake_event

    def to_data_lake_event(
        self,
        project_uuid: str,
        contact_urn: str,
        agent_data: Optional[dict] = None,
        tool_call_data: Optional[dict] = None,
        tool_result_data: Optional[dict] = None,
        preview: bool = False,
        backend: str = "openai",
        foundation_model: str = "",
        channel_uuid: Optional[str] = None,
        conversation: Optional[object] = None,
    ) -> Optional[dict]:
        if agent_data is None:
            agent_data = {}
        if tool_call_data is None:
            tool_call_data = {}
        if tool_result_data is None:
            tool_result_data = {}
        if preview or (not agent_data and not tool_call_data and not tool_result_data):
            return

        try:
            event_data = {
                "event_name": "weni_nexus_data",
                "date": pendulum.now("America/Sao_Paulo").to_iso8601_string(),
                "project": project_uuid,
                "contact_urn": contact_urn,
                "value_type": "string",
                "metadata": {"backend": backend, "foundation_model": foundation_model},
            }

            # Extract agent_identifier for agent_uuid lookup
            agent_identifier = None
            if agent_data:
                agent_identifier = agent_data.get("agent_name")

            if tool_result_data:
                event_data["metadata"]["tool_result"] = tool_result_data
                event_data["key"] = "tool_result"
                event_data["value"] = tool_result_data.get("tool_name", "")
                validated_event = self._event_service.send_validated_event(
                    event_data=event_data,
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    use_delay=False,
                    channel_uuid=channel_uuid,
                    agent_identifier=agent_identifier,
                    conversation=conversation,
                )
                return validated_event

            if tool_call_data:
                event_data["metadata"]["tool_call"] = tool_call_data
                event_data["key"] = "tool_call"
                event_data["value"] = tool_call_data["tool_name"]
                validated_event = self._event_service.send_validated_event(
                    event_data=event_data,
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    use_delay=False,
                    channel_uuid=channel_uuid,
                    agent_identifier=agent_identifier,
                    conversation=conversation,
                )
                return validated_event

            if agent_data:
                event_data["metadata"]["agent_collaboration"] = agent_data
                event_data["key"] = "agent_invocation"
                event_data["value"] = agent_data["agent_name"]
                validated_event = self._event_service.send_validated_event(
                    event_data=event_data,
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    use_delay=True,
                    channel_uuid=channel_uuid,
                    agent_identifier=agent_identifier,
                    conversation=conversation,
                )
                return validated_event

        except Exception as e:
            logger.error(f"Error processing data lake event: {str(e)}")
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return None

    def custom_event_data(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        event_data: list,
        preview: bool = False,
        agent_name: str = "",
        conversation: Optional[object] = None,
    ):
        """Delegate custom event processing to the service."""
        trace_data = {"project_uuid": project_uuid, "contact_urn": contact_urn}
        extractor = OpenAIEventExtractor(event_data=event_data, agent_name=agent_name)
        self._event_service.process_custom_events(
            trace_data=trace_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            extractor=extractor,
            preview=preview,
            conversation=conversation,
        )

    def to_data_lake_custom_event(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str] = None,
        conversation: Optional[object] = None,
    ) -> Optional[dict]:
        """Send a single custom event to data lake (for direct event sending, not from traces)."""
        return self._event_service.send_custom_event(
            event_data=event_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            conversation=conversation,
        )
