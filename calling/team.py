import asyncio
import json
from dataclasses import dataclass

import boto3
from agents import (
    Agent,
    FunctionTool,
    ModelSettings,
    RunContextWrapper,
    Runner,
)
from agents import Session as RealtimeSession
from agents import function_tool

from calling.clients.nexus import get_context, get_team
from calling.events import EventRegistry
from calling.sessions import Session

# from calling.functions import clean_schema, create_function_args_class


@dataclass
class Context:
    input_text: str
    credentials: dict
    globals: dict
    contact: dict
    project: dict
    content_base: dict
    session: RealtimeSession


context = get_context()
agents = get_team()


class ToolLambda:
    def __init__(self, function_name: str, agent_name: str, lambda_arn: str):
        self.function_name = function_name
        self.agent_name = agent_name
        self.lambda_arn = lambda_arn

    @classmethod
    async def _invoke_specific_lambda(cls, function_name: str, lambda_arn: str, args: dict): # TODO: Move to clients
        lambda_client = boto3.client("lambda", region_name="us-east-1")

        session_attributes = {
            "credentials": json.dumps(context.get("credentials")),
            "globals": json.dumps(context.get("globals")),
            "contact": json.dumps(context.get("contact")),
            "project": json.dumps(context.get("project")),
        }

        parameters = []
        try:
            for key, value in args.items():
                parameters.append({"name": key, "value": value})
        except Exception as error:
            traceback.print_exc()

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
            "function": lambda_arn,
            "messageVersion": "1.0",
        }

        payload_json = json.dumps(payload_json)

        try:
            response = await asyncio.to_thread(lambda_client.invoke, FunctionName=lambda_arn, InvocationType="RequestResponse", Payload=payload_json)
            lambda_result = response["Payload"].read().decode("utf-8")
            result = json.loads(lambda_result)
        except Exception as error:
            import traceback

            traceback.print_exc()
            return {"error": "Erro ao executar a lambda"}

        return result

    async def invoke_specific_lambda(self, ctx: RunContextWrapper[Context], args: str) -> str:
        args = json.loads(args)

        session = ctx.context.get("session")

        await EventRegistry.notify(
            "lambda.invocation.started",
            session=session,
            function_name=self.function_name,
            lambda_arn=self.lambda_arn,
            args=args,
        )

        result = await ToolLambda._invoke_specific_lambda(self.function_name, self.lambda_arn, args)

        await EventRegistry.notify(
            "lambda.invocation.completed",
            session=session,
            function_name=self.function_name,
            lambda_arn=self.lambda_arn,
            args=args,
            result=result,
        )

        return result


async def run_agent(session: "Session", agent_name, question):
    await EventRegistry.notify(
        "agent.run.started",
        session,
        agent_name=agent_name,
        input=question,
    )

    agent = agents.get(agent_name)

    result = await Runner.run(
        starting_agent=agent,
        input=question,
        context={"session": session},
    )

    await EventRegistry.notify(
        "agent.run.completed",
        session,
        agent_name=agent_name,
        output=result.final_output,
    )

    return result.final_output
