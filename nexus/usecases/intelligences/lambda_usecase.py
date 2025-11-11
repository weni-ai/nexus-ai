import boto3
import json
import logging
import sentry_sdk

from django.conf import settings
from django.core.exceptions import ValidationError

from nexus.intelligences.models import Conversation
from nexus.celery import app as celery_app
from nexus.projects.models import Project
from nexus.intelligences.producer.resolution_producer import ResolutionDTO, resolution_message

from router.services.message_service import MessageService
from router.repositories.entities import ResolutionEntities

from inline_agents.backends.bedrock.adapter import BedrockDataLakeEventAdapter

logger = logging.getLogger(__name__)


class LambdaUseCase():

    def __init__(self):
        self.boto_client = boto3.client('lambda', region_name=settings.AWS_BEDROCK_REGION_NAME)
        self.adapter = None
        self.task_manager = None

    def _get_data_lake_event_adapter(self):
        if self.adapter is None:
            self.adapter = BedrockDataLakeEventAdapter()
        return self.adapter

    def invoke_lambda(self, lambda_name: str, payload: dict):
        response = self.boto_client.invoke(
            FunctionName=lambda_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        return response

    def get_lambda_topics(self, project_uuid: str):
        from nexus.intelligences.models import Topics
        topics = Topics.objects.filter(project__uuid=project_uuid)
        topics_payload = []

        for topic in topics:
            subtopics_payload = []
            for subtopic in topic.subtopics.all():
                subtopics_payload.append({
                    "subtopic_uuid": str(subtopic.uuid),
                    "name": subtopic.name,
                    "description": subtopic.description
                })
            topics_payload.append({
                "topic_uuid": str(topic.uuid),
                "name": topic.name,
                "description": topic.description,
                "subtopics": subtopics_payload
            })

        return topics_payload

    def get_lambda_conversation(self, messages):
        conversation_payload = {
            "messages": []
        }

        for message in messages:
            conversation_payload["messages"].append({
                "sender": message['source'],
                "timestamp": str(message['created_at']),
                "content": message['text']
            })
        return conversation_payload

    def send_datalake_event(self, event_data: dict, project_uuid: str, contact_urn: str):
        adapter = self._get_data_lake_event_adapter()
        adapter.to_data_lake_custom_event(
            event_data=event_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn
        )

    def lambda_conversation_resolution(
        self,
        messages,
        has_chats_room: bool,
        project_uuid: str,
        contact_urn: str
    ):
        # If has_chats_room is True, skip lambda call and set resolution to "Has Chat Room"
        if has_chats_room:
            resolution = "Has Chat Room"
            event_data = {
                "event_name": "weni_nexus_data",
                "key": "conversation_classification",
                "value_type": "string",
                "value": resolution,
                "metadata": {
                    "human_support": has_chats_room,
                }
            }
            self.send_datalake_event(
                event_data=event_data,
                project_uuid=project_uuid,
                contact_urn=contact_urn
            )
            return resolution

        # Original logic for when has_chats_room is False
        lambda_conversation = messages
        payload_conversation = {
            "conversation": lambda_conversation
        }
        conversation_resolution = self.invoke_lambda(
            lambda_name=str(settings.CONVERSATION_RESOLUTION_NAME),
            payload=payload_conversation
        )
        conversation_resolution_response = json.loads(conversation_resolution.get("Payload").read()).get("body")
        resolution = conversation_resolution_response.get("result")
        event_data = {
            "event_name": "weni_nexus_data",
            "key": "conversation_classification",
            "value_type": "string",
            "value": resolution,
            "metadata": {
                "human_support": has_chats_room,
            }
        }
        self.send_datalake_event(
            event_data=event_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn
        )

        return conversation_resolution_response.get("result")

    def _is_valid_topic_uuid(self, topic_uuid_raw) -> bool:
        """
        Check if topic_uuid is valid (not None, not empty, not "None" string).
        """
        if not topic_uuid_raw:
            return False
        
        topic_uuid_str = str(topic_uuid_raw)
        invalid_values = {"", "None"}
        
        return topic_uuid_str not in invalid_values

    def lambda_conversation_topics(
        self,
        messages,
        has_chats_room: bool,
        project_uuid: str,
        contact_urn: str
    ):
        from nexus.intelligences.models import Topics

        lambda_topics = self.get_lambda_topics(project_uuid)
        lambda_conversation = messages

        payload_topics = {
            "topics": lambda_topics,
            "conversation": lambda_conversation
        }
        event_data = {
            "event_name": "weni_nexus_data",
            "key": "topics",
            "value_type": "string",
            "value": "bias",
            "metadata": {
                "topic_uuid": "",
                "subtopic_uuid": "",
                "subtopic": "",
                "human_support": has_chats_room,
            }
        }
        if len(lambda_topics) > 0:
            conversation_topics = self.invoke_lambda(
                lambda_name=str(settings.CONVERSATION_TOPIC_CLASSIFIER_NAME),
                payload=payload_topics
            )
            conversation_topics = json.loads(conversation_topics.get("Payload").read())
            conversation_topics = conversation_topics.get("body")
            topic_uuid_raw = conversation_topics.get("topic_uuid")
            
            # Update event_data if topic_uuid is valid
            if self._is_valid_topic_uuid(topic_uuid_raw):
                event_data = {
                    "event_name": "weni_nexus_data",
                    "key": "topics",
                    "value_type": "string",
                    "value": conversation_topics.get("topic_name"),
                    "metadata": {
                        "topic_uuid": str(topic_uuid_raw),
                        "subtopic_uuid": str(conversation_topics.get("subtopic_uuid")),
                        "subtopic": conversation_topics.get("subtopic_name"),
                        "human_support": has_chats_room,
                    }
                }

        self.send_datalake_event(
            event_data=event_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn
        )

        topic_uuid = event_data.get("metadata").get("topic_uuid")

        # Only try to get the topic if topic_uuid is valid
        if self._is_valid_topic_uuid(topic_uuid):
            try:
                topic = Topics.objects.get(uuid=topic_uuid)
                return topic
            except Topics.DoesNotExist:
                return None
            except ValidationError:
                # Invalid UUID format - return None instead of raising
                return None
        return None

    def _get_message_service(self):
        if self.task_manager is None:
            self.task_manager = MessageService()
        return self.task_manager

    def lambda_component_parser(
        self,
        final_response: str,
        use_components: bool
    ) -> str:
        if not use_components:
            return final_response

        prompt_type = "POST_PROCESSING"
        data = {
            "invokeModelRawResponse": f"<final_response>{final_response}</final_response>",
            "promptType": prompt_type,
        }
        response = self.invoke_lambda(
            lambda_name=str(settings.AWS_COMPONENTS_FUNCTION_ARN),
            payload=data
        )
        response = json.loads(response.get("Payload").read())
        parsed_final_response = response.get("postProcessingParsedResponse").get("responseText")
        return parsed_final_response

    def _transform_classification_item(self, item: dict) -> dict:
        """
        Transform a classification item to use 'name' instead of 'classification' key.
        """
        transformed_item = item.copy()
        
        if "classification" in transformed_item:
            transformed_item["name"] = transformed_item.pop("classification")
        elif "name" not in transformed_item:
            pass
        
        return transformed_item

    def _normalize_classification_data(self, classification_data: list, default_reason: str = "") -> list:
        """
        Normalize classification data to a consistent format with 'name' and 'reason' fields.
        Handles both list of dicts and list of strings.
        """
        if not classification_data:
            return []
        
        # If first item is a dict, transform all dict items
        if isinstance(classification_data[0], dict):
            return [
                self._transform_classification_item(item) if isinstance(item, dict) else item
                for item in classification_data
            ]
        
        # If it's a list of strings/values, convert to list of dicts
        return [
            {"name": classification_value, "reason": default_reason}
            for classification_value in classification_data
        ]

    def instruction_classify(
        self,
        name: str,
        occupation: str,
        goal: str,
        adjective: str,
        instructions: list,
        instruction_to_classify: str
    ):
        try:
            instructions_payload = {
                "name": name,
                "ocupation": occupation,
                "goal": goal,
                "adjective": adjective,
                "instructions": instructions,
                "instruction_to_classify": instruction_to_classify
            }
            
            response = self.invoke_lambda(
                lambda_name=str(settings.INSTRUCTION_CLASSIFY_NAME),
                payload=instructions_payload
            )
            
            if 'FunctionError' in response:
                error_payload = json.loads(response.get("Payload").read())
                error_type = error_payload.get("errorType", "Unknown")
                error_message = error_payload.get("errorMessage", "Unknown error")

                sentry_sdk.set_context("lambda_error", {
                    "lambda_name": str(settings.INSTRUCTION_CLASSIFY_NAME),
                    "full_error_payload": error_payload,
                    "error_type": error_type    ,
                    "error_message": error_message,
                    "stack_trace": error_payload.get("stackTrace", []),
                    "request_payload": instructions_payload
                })
                sentry_sdk.capture_message(
                    f"Lambda FunctionError in instruction_classify: {error_payload}",
                    level="error"
                )
                
                raise Exception(f"Lambda error ({error_type}): {error_message}")
            
            response_data = json.loads(response.get("Payload").read())
            
            # Check if response has a body wrapper
            if "body" in response_data:
                body_data = response_data.get("body")
                if isinstance(body_data, str):
                    body_data = json.loads(body_data)
                response_data = body_data
            
            # Check for error responses from lambda
            status_code = response_data.get("statusCode")
            if status_code and status_code >= 400:
                error_message = response_data.get("error") or response_data.get("message", "Unknown error from lambda")
                
                sentry_sdk.set_context("lambda_error", {
                    "lambda_name": str(settings.INSTRUCTION_CLASSIFY_NAME),
                    "status_code": status_code,
                    "error_message": error_message,
                    "full_response": response_data,
                    "request_payload": instructions_payload
                })
                sentry_sdk.capture_message(
                    f"Lambda returned error status {status_code} in instruction_classify: {error_message}",
                    level="error"
                )
                
                raise Exception(f"Lambda error (status {status_code}): {error_message}")

            classification_data = response_data.get("classifications") or response_data.get("classification", [])
            suggestion = response_data.get("suggestion")
            reason = response_data.get("reason", "")
            
            # Normalize classification data to consistent format
            classification = self._normalize_classification_data(classification_data, reason)
            
            return classification, suggestion
            
        except Exception as e:
            sentry_sdk.capture_exception(e)
            raise e


@celery_app.task(bind=True)
def create_lambda_conversation(
    self,
    payload: dict,
):
    task_id = self.request.id
    correlation_id = payload.get("correlation_id", "unknown")
    project_uuid = payload.get("project_uuid")
    contact_urn = payload.get("contact_urn")
    external_id = payload.get("external_id")
    
    logger.info(
        "[create_lambda_conversation] Task started",
        extra={
            "task_id": task_id,
            "correlation_id": correlation_id,
            "project_uuid": project_uuid,
            "contact_urn": contact_urn,
            "external_id": external_id,
            "task_name": "create_lambda_conversation"
        }
    )

    try:
        project = Project.objects.get(uuid=payload.get("project_uuid"))
        
        if not project.brain_on:
            return

        lambda_usecase = LambdaUseCase()
        message_service = lambda_usecase._get_message_service()

        # Use new conversation-based message retrieval
        messages = message_service.get_messages_for_conversation(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=payload.get("channel_uuid"),
            # If any errors happen to an older conversation, we will get all messages for correct conversation
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
        )

        if not messages:
            logger.warning(
                "[create_lambda_conversation] No messages found",
                extra={
                    "task_id": task_id,
                    "correlation_id": correlation_id,
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "task_name": "create_lambda_conversation"
                }
            )
            raise ValueError("No unclassified messages found for conversation period")

        project = Project.objects.get(uuid=project_uuid)
        conversation_queryset = Conversation.objects.filter(
            project=project,
            contact_urn=contact_urn,
            channel_uuid=payload.get("channel_uuid"),
            resolution=ResolutionEntities.IN_PROGRESS
        )

        formated_messages = lambda_usecase.get_lambda_conversation(messages)
        
        logger.info(
            "[create_lambda_conversation] Invoking resolution lambda",
            extra={
                "task_id": task_id,
                "correlation_id": correlation_id,
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "messages_count": len(messages),
                "task_name": "create_lambda_conversation"
            }
        )
        
        resolution = lambda_usecase.lambda_conversation_resolution(
            messages=formated_messages,
            has_chats_room=payload.get("has_chats_room"),
            project_uuid=project_uuid,
            contact_urn=contact_urn
        )

        contact_name = payload.get("name")
        resolution_choice_value = ResolutionEntities.convert_resolution_string_to_int(resolution)

        resolution_dto = ResolutionDTO(
            resolution=resolution_choice_value,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            external_id=external_id
        )
        
        # Log when sending unclassified conversations to billing
        if resolution_choice_value == ResolutionEntities.UNCLASSIFIED:
            logging.info(
                f"[Billing] Sending unclassified conversation to billing - "
                f"project_uuid: {project_uuid}, "
                f"contact_urn: {contact_urn}, "
                f"external_id: {external_id}, "
                f"resolution: {resolution_choice_value}"
            )
        logger.info(
            "[create_lambda_conversation] Sending resolution to billing",
            extra={
                "task_id": task_id,
                "correlation_id": correlation_id,
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "external_id": external_id,
                "resolution": resolution_choice_value,
                "resolution_name": ResolutionEntities.resolution_mapping(resolution_choice_value)[1],
                "task_name": "create_lambda_conversation"
            }
        )
        
        resolution_message(resolution_dto)
        
        # Get topic after billing message is sent
        topic = lambda_usecase.lambda_conversation_topics(
            messages=formated_messages,
            has_chats_room=payload.get("has_chats_room"),
            project_uuid=project_uuid,
            contact_urn=contact_urn
        )


        update_data = {
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "has_chats_room": payload.get("has_chats_room"),
            "external_id": external_id,
            "resolution": resolution_choice_value,
            "topic": topic
        }
        
        if contact_name:
            update_data["contact_name"] = contact_name
        
        conversation_queryset.update(**update_data)

        message_service.clear_message_cache(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=payload.get("channel_uuid")
        )
        
        logger.info(
            "[create_lambda_conversation] Task completed successfully",
            extra={
                "task_id": task_id,
                "correlation_id": correlation_id,
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "external_id": external_id,
                "resolution": resolution_choice_value,
                "task_name": "create_lambda_conversation"
            }
        )

    except Exception as e:
        logger.error(
            "[create_lambda_conversation] Task failed",
            extra={
                "task_id": task_id,
                "correlation_id": correlation_id,
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "external_id": external_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "task_name": "create_lambda_conversation"
            },
            exc_info=True
        )
        
        agent_uuid = None
        try:
            from nexus.inline_agents.models import IntegratedAgent
            
            project_uuid = payload.get("project_uuid")
            if project_uuid:
                integrated_agent = IntegratedAgent.objects.filter(
                    project__uuid=project_uuid
                ).select_related('agent').first()
                
                if integrated_agent:
                    agent_uuid = str(integrated_agent.agent.uuid)
        except Exception:
            pass
        
        sentry_context = {
            "payload": payload,
            "task_id": task_id,
            "correlation_id": correlation_id
        }
        
        if agent_uuid:
            sentry_context["agent_uuid"] = agent_uuid
        
        sentry_sdk.set_context(
            "conversation_context",
            sentry_context
        )
        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_tag("contact_urn", contact_urn)
        sentry_sdk.set_tag("task_id", task_id)
        sentry_sdk.set_tag("correlation_id", correlation_id)
        sentry_sdk.set_tag("channel_uuid", payload.get("channel_uuid"))
        
        if agent_uuid:
            sentry_sdk.set_tag("agent_uuid", agent_uuid)
        
        sentry_sdk.capture_exception(e)
