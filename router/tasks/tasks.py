# ruff: noqa: E501
import json
import logging
import os
import time
from typing import Dict, List, Optional

from django.conf import settings
from django.template.defaultfilters import slugify
from openai import OpenAI
from redis import Redis
from tenacity import retry, stop_after_attempt, wait_exponential

from nexus.agents.models import AgentMessage
from nexus.celery import app as celery_app
from nexus.intelligences.llms.client import LLMClient
from nexus.projects.models import Project
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from nexus.usecases.agents.agents import AgentUsecase
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
    get_llm_by_project_uuid,
)
from nexus.usecases.intelligences.retrieve import get_file_info
from nexus.usecases.logs.create import CreateLogUsecase
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from router.classifiers.chatgpt_function import ChatGPTFunctionClassifier
from router.classifiers.classification import Classification
from router.classifiers.pre_classification import PreClassification
from router.clients.flows.http.flow_start import FlowStartHTTPClient
from router.clients.flows.http.send_message import (
    SendMessageHTTPClient,
)
from router.clients.preview.simulator.broadcast import SimulateBroadcast
from router.clients.preview.simulator.flow_start import SimulateFlowStart
from router.dispatcher import dispatch
from router.entities import (
    AgentDTO,
    ContentBaseDTO,
    LLMSetupDTO,
    message_factory,
)
from router.repositories.orm import (
    ContentBaseORMRepository,
    FlowsORMRepository,
    MessageLogsRepository,
)
from router.route import route

from .actions_client import get_action_clients

client = OpenAI()
logger = logging.getLogger(__name__)
flows_user_email = settings.FLOW_USER_EMAIL


def improve_rationale_text(
    rationale_text: str,
    previous_rationales: Optional[list] = None,
    user_input: str = "",
    is_first_rationale: bool = False,
) -> str:
    if previous_rationales is None:
        previous_rationales = []
    try:
        # Get the Bedrock runtime client
        bedrock_db = BedrockFileDatabase()
        bedrock_client = bedrock_db._BedrockFileDatabase__get_bedrock_runtime()

        # Set the model ID for Amazon Nova Lite
        model_id = settings.AWS_RATIONALE_MODEL

        # Prepare the complete instruction content for the user message
        instruction_content = """
            You are an agent specialized in sending notifications to your user. They are waiting for a response to a request, but before receiving it, you need to notify them with precision about what you're doing, in a way that truly helps them. To do this, you will receive a thought and should rephrase it by following principles to make it fully useful to the user.

            The thought you will receive to rephrase will be between the <thought><thought> tags.

            You can also use the user's message to base the rephrasing of the thought. The user's message will be between the <user_message></user_message> tags.

            For the rephrasing, you must follow principles. These will be between the <principles></principles> tags, and you should give them high priority.

            <principles>
            - Keeping it concise and direct (max 15 words);
            - The rephrasing should always be in the first person (you are the one thinking);
            - Your output is always in the present tense;
            - Removing conversation starters and technical jargon;
            - Clearly stating the current action or error condition;
            - Preserving essential details from the original rationale;
            - Returning ONLY the transformed text with NO additional explanation or formatting;- Your output should ALWAYS be in the language of the user's message.
            </principles>

            You can find examples of rephrasings within the tags <examples></examples>.

            <examples>
            # EXAMPLE 1
            Tought: Consulting ProductConcierge for formal clothing suggestions.
            Rephrasing: I'm looking for formal clothes for you!
            # EXAMPLE 2
            Tought: The user is looking for flights from Miami to New York for one person, with specific dates. I will use the travel agent to search for this information.
            Rephrasing: Checking flights from Miami to New York on specified dates.
            # EXAMPLE 3
            Tought: I received an error because the provided dates are in the past. I need to inform the user that future dates are required for the search.
            Rephrasing: Dates provided are in the past, future dates needed.</examples>
        """

        if user_input:
            instruction_content += f"""
                <user_message>{user_input}</user_message>
            """

        # Add the rationale text to analyze
        instruction_content += f"""
            <thought>{rationale_text}</thought>
        """

        # Build conversation with just one user message and an expected assistant response
        conversation = [
            # Single user message with all instructions and the rationale to analyze
            {"role": "user", "content": [{"text": instruction_content}]}
        ]

        # Send the request to Amazon Bedrock
        response = bedrock_client.converse(
            modelId=model_id, messages=conversation, inferenceConfig={"maxTokens": 150, "temperature": 0.5, "topP": 0.9}
        )

        logger.debug("Improvement response", extra={"length": len(str(response or ""))})
        # Extract the response text
        response_text = response["output"]["message"]["content"][0]["text"]

        # For first rationales, make sure they're never "invalid"
        if is_first_rationale and response_text.strip().lower() == "invalid":
            # If somehow still got "invalid", force a generic improvement
            return "Processando sua solicitação agora."

        # Remove any quotes from the response
        return response_text.strip().strip("\"'")
    except Exception as e:
        logger.error("Error improving rationale text: %s", str(e))
        return rationale_text  # Return original text if transformation fails


def improve_subsequent_rationale(
    rationale_text: str, previous_rationales: Optional[list] = None, user_input: str = ""
) -> str:
    if previous_rationales is None:
        previous_rationales = []
    try:
        # Get the Bedrock runtime client
        bedrock_db = BedrockFileDatabase()
        bedrock_client = bedrock_db._BedrockFileDatabase__get_bedrock_runtime()

        # Set the model ID for Amazon Nova Lite
        model_id = settings.AWS_RATIONALE_MODEL

        # Prepare the complete instruction content for the user message
        instruction_content = """
            You are a message analyst responsible for reviewing messages from an artificial agent that may or may not be sent to the end user.

            You will receive the agent's main thought, and your first task is to determine whether this thought is invalid for sending to the end user. The main thought will be enclosed within the tags <main_thought></main_thought>.

            To decide if a thought is valid, you must analyze a list of criteria that classify a thought as invalid, as well as review previous thoughts. These previous thoughts will be enclosed within the tags <previous_thought></previous_thought>. The list of criteria you must analyze to determine if a thought is invalid will be enclosed within the tags <invalid_thought></invalid_thought>. Another important piece of information for your analysis is the user's message, which will be enclosed within the tags <user_message></user_message>.

            <invalid_thought>
                - Contains greetings, generic assistance, or simple acknowledgments
                - Mentions internal components (e.g., "ProductConcierge") without adding value
                - Describes communication actions with the user (e.g., "I will inform the user")
                - Is vague, generic, or lacks specific actionable content
                - Conveys essentially the same information as any previous rationale, even if worded differently
                - Addresses the same topic or message as the immediately previous rationale
            </invalid_thought>

            If the thought is considered invalid, write only 'invalid'. Write NOTHING else besides 'invalid'.

            If the thought is valid, you must REWRITE IT following the rewriting principles. These principles will be within the tags <principles></principles> and must be HIGHLY prioritized if the thought is considered valid.

            <principles>
                - Keeping it concise and direct (max 15 words);
                - The rephrasing should always be in the first person (you are the one thinking);
                - Your output is always in the present tense;
                - Removing conversation starters and technical jargon;
                - Clearly stating the current action or error condition;
                - Preserving essential details from the original rationale;
                - Returning ONLY the transformed text with NO additional explanation or formatting;
                - Your output should ALWAYS be in the language of the user's message.
            </principles>

            You can find examples of rephrasings within the tags <examples></examples>.

            <examples>
            # EXAMPLE 1
            Tought: Consulting ProductConcierge for formal clothing suggestions.
            Rephrasing: I'm looking for formal clothes for you!
            # EXAMPLE 2
            Tought: The user is looking for flights from Miami to New York for one person, with specific dates. I will use the travel agent to search for this information.
            Rephrasing: Checking flights from Miami to New York on specified dates.
            # EXAMPLE 3
            Tought: I received an error because the provided dates are in the past. I need to inform the user that future dates are required for the search.
            Rephrasing: Dates provided are in the past, future dates needed.
            </examples>
        """

        # Add user input context if available
        if user_input:
            instruction_content += f"<user_message>{user_input}</user_message>"

        if previous_rationales:
            instruction_content += f"""
            <previous_thought>
            {' '.join([f"- {r}" for r in previous_rationales])}
            </previous_thought>
            """

        # Add the rationale text to analyze
        instruction_content += f"<main_thought>{rationale_text}</main_thought>"

        # Build conversation with just one user message and an expected assistant response
        conversation = [
            # Single user message with all instructions and the rationale to analyze
            {"role": "user", "content": [{"text": instruction_content}]}
        ]

        # Send the request to Amazon Bedrock
        response = bedrock_client.converse(
            modelId=model_id, messages=conversation, inferenceConfig={"maxTokens": 150, "temperature": 0}
        )

        # Extract the response text
        response_text = response["output"]["message"]["content"][0]["text"]

        # Remove any quotes from the response
        return response_text.strip().strip("\"'")
    except Exception as e:
        logger.error(f"Error improving subsequent rationale text: {str(e)}")
        return rationale_text  # Return original text if transformation fails


@celery_app.task
def task_send_message_http_client(
    text: str, urns: list, project_uuid: str, user: str, full_chunks: list[Dict] = None
) -> None:
    broadcast = SendMessageHTTPClient(
        os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_SEND_MESSAGE_INTERNAL_TOKEN")
    )

    broadcast.send_direct_message(text=text, urns=urns, project_uuid=project_uuid, user=user, full_chunks=full_chunks)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_trace_summary(language, trace):
    try:
        # Add a small delay between API calls to respect rate limits
        if settings.TRACE_SUMMARY_DELAY:
            time.sleep(3)

        prompt = f"""
          Generate a concise, one-line summary of the trace of the action, in {language}.
          This summary must describe the orchestrator's action, referring to all actions as "skills."

          Guidelines for your response:
          - Use the following language for the summary: {language}.
          - The text to be summarized is the trace of the action.
          - Use a systematic style (e.g., "Cancel Order skill activated", "Forwarding request to Reporting skill").
          - The summary must not exceed 10 words.
          - Use varied gerunds (e.g., "Checking", "Cancelling", "Forwarding").
          - Do not include technical details about models, architectures, language codes, or anything unrelated to summarizing the action.

          Here is the trace of the action:
          {json.dumps(trace, indent=2)}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini", max_tokens=100, messages=[{"role": "user", "content": prompt}]
        )

        return response.choices[0].message.content
    except Exception as e:
        logger.error("Error getting trace summary: %s", str(e), exc_info=True)
        return "Processing your request now"


@celery_app.task(
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def start_route(self, message: Dict, preview: bool = False) -> bool:  # pragma: no cover
    # TODO: remove get_action_clients from this function
    def get_action_clients(preview: bool = False):
        if preview:
            flow_start = SimulateFlowStart(
                os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN")
            )
            broadcast = SimulateBroadcast(
                os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN"), get_file_info
            )
            return broadcast, flow_start

        broadcast = SendMessageHTTPClient(
            os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_SEND_MESSAGE_INTERNAL_TOKEN")
        )
        flow_start = FlowStartHTTPClient(os.environ.get("FLOWS_REST_ENDPOINT"), os.environ.get("FLOWS_INTERNAL_TOKEN"))
        return broadcast, flow_start

    source = "preview" if preview else "router"
    logger.info("Message source", extra={"source": source})

    # Initialize Redis client using the REDIS_URL from settings
    redis_client = Redis.from_url(settings.REDIS_URL)

    logger.info("Message received", extra={"has_text": bool(message.get("text"))})

    content_base_repository = ContentBaseORMRepository()
    message_logs_repository = MessageLogsRepository()

    message = message_factory(
        project_uuid=message.get("project_uuid"),
        text=message.get("text"),
        contact_urn=message.get("contact_urn"),
        metadata=message.get("metadata"),
        attachments=message.get("attachments"),
        msg_event=message.get("msg_event"),
        contact_fields=message.get("contact_fields", {}),
    )

    mailroom_msg_event = message.msg_event
    mailroom_msg_event["attachments"] = mailroom_msg_event.get("attachments") or []
    mailroom_msg_event["metadata"] = mailroom_msg_event.get("metadata") or {}

    log_usecase = CreateLogUsecase()

    try:
        project_uuid: str = message.project_uuid
        indexer = ProjectsUseCase().get_indexer_database_by_uuid(project_uuid)
        flows_repository = FlowsORMRepository(project_uuid=project_uuid)

        broadcast, flow_start = get_action_clients(preview)

        content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(message.project_uuid)
        agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
        agent = agent.set_default_if_null()

        pre_classification = PreClassification(
            flows_repository=flows_repository,
            message=message,
            msg_event=mailroom_msg_event,
            flow_start=flow_start,
            user_email=flows_user_email,
        )

        pre_classification = pre_classification.pre_classification(source=source)
        if pre_classification:
            return pre_classification if source == "preview" else True

        classification_handler = Classification(
            flows_repository=flows_repository,
            message=message,
            msg_event=mailroom_msg_event,
            flow_start=flow_start,
            user_email=flows_user_email,
        )

        non_custom_actions = classification_handler.non_custom_actions(source=source)
        if non_custom_actions:
            return non_custom_actions if source == "preview" else True

        message_log = log_usecase.create_message_log(
            text=message.text,
            contact_urn=message.contact_urn,
            source=source,
        )

        llm_model = get_llm_by_project_uuid(project_uuid)

        llm_config = LLMSetupDTO(
            model=llm_model.model.lower(),
            model_version=llm_model.setup.get("version"),
            temperature=llm_model.setup.get("temperature"),
            top_k=llm_model.setup.get("top_k"),
            top_p=llm_model.setup.get("top_p"),
            token=llm_model.setup.get("token"),
            max_length=llm_model.setup.get("max_length"),
            max_tokens=llm_model.setup.get("max_tokens"),
            language=llm_model.setup.get("language", settings.WENIGPT_DEFAULT_LANGUAGE),
        )

        classifier = ChatGPTFunctionClassifier(agent_goal=agent.goal)

        classification = classification_handler.custom_actions(classifier=classifier, language=llm_config.language)

        llm_client = LLMClient.get_by_type(llm_config.model)
        llm_client: LLMClient = list(llm_client)[0](model_version=llm_config.model_version, api_key=llm_config.token)

        # Check if there's a pending response for this user
        pending_response_key = f"response:{message.contact_urn}"
        pending_task_key = f"task:{message.contact_urn}"
        pending_response = redis_client.get(pending_response_key)
        pending_task_id = redis_client.get(pending_task_key)

        if pending_response:
            # Revoke the previous task
            if pending_task_id:
                celery_app.control.revoke(pending_task_id.decode("utf-8"), terminate=True)

            # Concatenate the previous message with the new one
            previous_message = pending_response.decode("utf-8")
            concatenated_message = f"{previous_message}\n{message.text}"
            message.text = concatenated_message
            redis_client.delete(pending_response_key)  # Remove the pending response
        else:
            # Store the current message in Redis
            redis_client.set(pending_response_key, message.text)

        # Store the current task ID in Redis
        redis_client.set(pending_task_key, self.request.id)

        # Generate response for the concatenated message
        response: dict = route(
            classification=classification,
            message=message,
            content_base_repository=content_base_repository,
            flows_repository=flows_repository,
            message_logs_repository=message_logs_repository,
            indexer=indexer(),
            llm_client=llm_client,
            direct_message=broadcast,
            flow_start=flow_start,
            llm_config=llm_config,
            flows_user_email=flows_user_email,
            log_usecase=log_usecase,
            message_log=message_log,
        )

        # If response generation completes, remove from Redis
        redis_client.delete(pending_response_key)
        redis_client.delete(pending_task_key)

        log_usecase.update_status("S")

        return response

    except Exception as e:
        logger.error("START ROUTE error: %s", e, exc_info=True)
        if message.text:
            log_usecase.update_status("F", exception_text=e)
        raise


def _initialize_and_handle_pending_response(message, task_id):
    redis_client = Redis.from_url(settings.REDIS_URL)
    message = message_factory(
        project_uuid=message.get("project_uuid"),
        text=message.get("text"),
        contact_urn=message.get("contact_urn"),
        metadata=message.get("metadata"),
        attachments=message.get("attachments"),
        msg_event=message.get("msg_event"),
        contact_fields=message.get("contact_fields", {}),
    )

    pending_response_key = f"multi_response:{message.contact_urn}"
    pending_task_key = f"multi_task:{message.contact_urn}"
    pending_response = redis_client.get(pending_response_key)
    pending_task_id = redis_client.get(pending_task_key)

    if pending_response:
        if pending_task_id:
            celery_app.control.revoke(pending_task_id.decode("utf-8"), terminate=True)
        previous_message = pending_response.decode("utf-8")
        concatenated_message = f"{previous_message}\n{message.text}"
        message.text = concatenated_message
        redis_client.delete(pending_response_key)
    else:
        redis_client.set(pending_response_key, message.text)

    redis_client.set(pending_task_key, task_id)
    return redis_client, message


def _process_event(
    event,
    user_email,
    session_id,
    project_uuid,
    language,
    preview,
    full_response,
    trace_events,
    first_rationale_text,
    is_first_rationale,
    rationale_history,
    should_process_rationales,
    message,
    flows_user_email,
):
    if event["type"] == "chunk":
        chunk = event["content"]
        full_response += chunk
        if user_email:
            send_preview_message_to_websocket(
                project_uuid=str(project_uuid),
                user_email=user_email,
                message_data={"type": "chunk", "content": chunk, "session_id": session_id},
            )
    elif event["type"] == "trace":
        _process_trace_event(
            event,
            user_email,
            session_id,
            project_uuid,
            language,
            preview,
            trace_events,
            first_rationale_text,
            is_first_rationale,
            rationale_history,
            should_process_rationales,
            message,
            flows_user_email,
        )
    return full_response


def _process_trace_event(
    event,
    user_email,
    session_id,
    project_uuid,
    language,
    preview,
    trace_events,
    first_rationale_text,
    is_first_rationale,
    rationale_history,
    should_process_rationales,
    message,
    flows_user_email,
):
    if preview:
        event["content"]["summary"] = get_trace_summary(language, event["content"])
        if user_email:
            send_preview_message_to_websocket(
                project_uuid=str(project_uuid),
                user_email=user_email,
                message_data={"type": "trace_update", "trace": event["content"], "session_id": session_id},
            )
    trace_events.append(event["content"])
    trace_data = event["content"]
    try:
        if should_process_rationales:
            _handle_rationale_processing(
                trace_data,
                first_rationale_text,
                is_first_rationale,
                rationale_history,
                message,
                flows_user_email,
                project_uuid,
            )

        event["content"]["summary"] = get_trace_summary(language, event["content"])
        if user_email:
            send_preview_message_to_websocket(
                project_uuid=str(project_uuid),
                user_email=user_email,
                message_data={"type": "trace_update", "trace": event["content"], "session_id": session_id},
            )
    except Exception as e:
        logger.error(f"Error processing rationale: {str(e)}")
        if user_email:
            send_preview_message_to_websocket(
                project_uuid=str(project_uuid),
                user_email=user_email,
                message_data={
                    "type": "error",
                    "content": f"Error processing rationale: {str(e)}",
                    "session_id": session_id,
                },
            )


def _handle_rationale_processing(
    trace_data, first_rationale_text, is_first_rationale, rationale_history, message, flows_user_email, project_uuid
):
    if first_rationale_text and "callerChain" in trace_data:
        caller_chain = trace_data["callerChain"]
        if isinstance(caller_chain, list) and len(caller_chain) > 1:
            improved_text = improve_rationale_text(
                first_rationale_text, rationale_history, message.text, is_first_rationale=True
            )
            if improved_text.lower() != "invalid":
                rationale_history.append(improved_text)
                task_send_message_http_client.delay(
                    text=improved_text,
                    urns=[message.contact_urn],
                    project_uuid=str(project_uuid),
                    user=flows_user_email,
                )

    rationale_text = None
    if "trace" in trace_data:
        inner_trace = trace_data["trace"]
        if "orchestrationTrace" in inner_trace:
            orchestration = inner_trace["orchestrationTrace"]
            if "rationale" in orchestration:
                rationale_text = orchestration["rationale"].get("text")

    if rationale_text:
        if is_first_rationale:
            first_rationale_text = rationale_text
            is_first_rationale = False
        else:
            improved_text = improve_subsequent_rationale(rationale_text, rationale_history, message.text)
            if improved_text.lower() != "invalid":
                rationale_history.append(improved_text)
                task_send_message_http_client.delay(
                    text=improved_text,
                    urns=[message.contact_urn],
                    project_uuid=str(project_uuid),
                    user=flows_user_email,
                )


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360)
def start_multi_agents(
    self, message: Dict, preview: bool = False, language: str = "en", user_email: str = ""
) -> bool:  # pragma: no cover
    redis_client, message = _initialize_and_handle_pending_response(message, self.request.id)

    project = Project.objects.get(uuid=message.project_uuid)
    supervisor = project.team
    supervisor_version = supervisor.current_version
    contentbase = get_default_content_base_by_project(message.project_uuid)
    usecase = AgentUsecase()

    session_id = f"project-{project.uuid}-session-{message.sanitized_urn}"
    session_id = slugify(session_id)

    pending_response_key = f"multi_response:{message.contact_urn}"
    pending_task_key = f"multi_task:{message.contact_urn}"

    if user_email:
        # Send initial status through WebSocket
        send_preview_message_to_websocket(
            project_uuid=str(project.uuid),
            user_email=user_email,
            message_data={"type": "status", "content": "Starting multi-agent processing", "session_id": session_id},
        )

    project_use_components = message.project_uuid in settings.PROJECT_COMPONENTS

    try:
        # Stream supervisor response
        broadcast, _ = get_action_clients(
            preview,
            multi_agents=True,
            project_use_components=project_use_components,
            project_uuid=str(message.project_uuid),
            stream_support=getattr(message, "stream_support", False),
        )
        logger.info("Starting multi-agents")

        full_chunks = []
        rationale_history = []
        full_response = ""
        trace_events = []

        first_rationale_text = None
        is_first_rationale = True
        should_process_rationales = supervisor.metadata.get("rationale", False)

        for event in usecase.invoke_supervisor_stream(
            session_id=session_id,
            supervisor_id=supervisor.external_id,
            supervisor_alias_id=supervisor_version.alias_id,
            message=message,
            content_base=contentbase,
        ):
            full_response = _process_event(
                event,
                user_email,
                session_id,
                message.project_uuid,
                language,
                preview,
                full_response,
                trace_events,
                first_rationale_text,
                is_first_rationale,
                rationale_history,
                should_process_rationales,
                message,
                flows_user_email,
            )

        save_trace_events.delay(
            trace_events,
            str(project.uuid),
            str(project.team.id),
            message.text,
            message.contact_urn,
            full_response,
            preview,
            session_id,
        )
        if user_email:
            # Send completion status
            send_preview_message_to_websocket(
                user_email=user_email,
                project_uuid=str(project.uuid),
                message_data={"type": "status", "content": "Processing complete", "session_id": session_id},
            )

        # Clean up Redis entries after successful processing
        redis_client.delete(pending_response_key)
        redis_client.delete(pending_task_key)

        return dispatch(
            llm_response=full_response,
            message=message,
            direct_message=broadcast,
            user_email=flows_user_email,
            full_chunks=full_chunks,
        )

    except Exception as e:
        # Clean up Redis entries in case of error
        redis_client.delete(pending_response_key)
        redis_client.delete(pending_task_key)

        logger.error("Error in start_multi_agents: %s", str(e), exc_info=True)

        if user_email:
            # Send error status through WebSocket
            send_preview_message_to_websocket(
                user_email=user_email,
                project_uuid=str(project.uuid),
                message_data={"type": "error", "content": str(e), "session_id": session_id},
            )
        raise


def trace_events_to_json(trace_event):
    return json.dumps(trace_event, default=str)


@celery_app.task()
def save_trace_events(
    trace_events: List[Dict],
    project_uuid: str,
    team_id: str,
    user_text: str,
    contact_urn: str,
    agent_response: str,
    preview: bool,
    session_id: str,
):
    source = {True: "preview", False: "router"}
    data = ""
    message = AgentMessage.objects.create(
        project_id=project_uuid,
        team_id=team_id,
        user_text=user_text,
        agent_response=agent_response,
        contact_urn=contact_urn,
        source=source.get(preview),
        session_id=session_id,
    )

    filename = f"{message.uuid}.jsonl"

    for trace_event in trace_events:
        trace_events_json = trace_events_to_json(trace_event)
        data += trace_events_json + "\n"

    key = f"traces/{project_uuid}/{filename}"
    BedrockFileDatabase().upload_traces(data, key)
