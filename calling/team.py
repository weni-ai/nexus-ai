import asyncio
import json
import traceback
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


async def call_lambda(context: dict, function_name: str, lambda_arn: str, args: dict):
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


async def invoke_specific_lambda(ctx: RunContextWrapper[Context], args: str) -> str:
    context = ctx.context
    args = json.loads(args)

    session = context.get("session")

    function_name = ctx.tool_name
    tool = session.agents["functions"].get(function_name)
    lambda_arn = tool.function_arn

    await EventRegistry.notify(
        "lambda.invocation.started",
        session=session,
        function_name=function_name,
        lambda_arn=lambda_arn,
        args=args,
    )

    result = await call_lambda(context, function_name, lambda_arn, args)

    await EventRegistry.notify(
        "lambda.invocation.completed",
        session=session,
        function_name=function_name,
        lambda_arn=lambda_arn,
        args=args,
        result=result,
    )

    return result


async def run_agent(session: "Session", agent_name: str, args: dict):
    print("Rodando um agente/function", agent_name, args)
    await EventRegistry.notify(
        "agent.run.started",
        session,
        agent_name=agent_name,
        args=args,
    )

    context = {"session": session, **session.agents.get("context", {})}

    agent: Agent = session.agents.get("team", {}).get(agent_name)

    if agent is not None:
        agent.hooks = None
        
        for tool in agent.tools:
            tool.on_invoke_tool = invoke_specific_lambda

        # print(agent.tools[0].function_arn)
        # TODO pegar o lambda ARN

        print("Executando agente")
        result = await Runner.run(
            starting_agent=agent,
            input=args.get("question"),
            context=context,
        )

        return result.final_output

    manager_functions_arns = session.agents.get("manager_functions_arns")
    lambda_arn = manager_functions_arns.get(agent_name)
    print("Lambda selecionada:", lambda_arn)

    if not lambda_arn:
        return "Agente não encontrado"

    print("Executando Lambda")
    result = await call_lambda(context, agent_name, lambda_arn, args)
    print("Result:", result)
    return result
