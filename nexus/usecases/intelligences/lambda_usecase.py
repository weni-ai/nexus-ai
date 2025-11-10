import boto3
import json
import logging
import sentry_sdk

from django.conf import settings

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

            if conversation_topics.get("topic_uuid") != "":
                event_data = {
                    "event_name": "weni_nexus_data",
                    "key": "topics",
                    "value_type": "string",
                    "value": conversation_topics.get("topic_name"),
                    "metadata": {
                        "topic_uuid": str(conversation_topics.get("topic_uuid")),
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

        # Only try to get the topic if topic_uuid is not empty
        if topic_uuid and topic_uuid != "":
            try:
                topic = Topics.objects.get(uuid=topic_uuid)
                return topic
            except Topics.DoesNotExist:
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


@celery_app.task
def create_lambda_conversation(
    payload: dict,
):

    try:
        project_uuid = payload.get("project_uuid")
        contact_urn = payload.get("contact_urn")
        channel_uuid = payload.get("channel_uuid")
        
        # Check if project has brain_on enabled
        try:
            project = Project.objects.get(uuid=project_uuid)
            if not project.brain_on:
                logger.info(
                    f"[Billing] Skipping conversation processing - brain_on is False - "
                    f"project_uuid: {project_uuid}, contact_urn: {contact_urn}"
                )
                return
        except Project.DoesNotExist:
            logger.error(
                f"[Billing] Project not found - project_uuid: {project_uuid}, contact_urn: {contact_urn}"
            )
            raise
        
        lambda_usecase = LambdaUseCase()
        message_service = lambda_usecase._get_message_service()

        # Use new conversation-based message retrieval
        messages = message_service.get_messages_for_conversation(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            # If any errors happen to an older conversation, we will get all messages for correct conversation
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
        )

        if not messages:
            raise ValueError("No unclassified messages found for conversation period")

        conversation_queryset = Conversation.objects.filter(
            project=project,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            resolution=ResolutionEntities.IN_PROGRESS
        )

        formated_messages = lambda_usecase.get_lambda_conversation(messages)
        resolution = lambda_usecase.lambda_conversation_resolution(
            messages=formated_messages,
            has_chats_room=payload.get("has_chats_room"),
            project_uuid=project_uuid,
            contact_urn=contact_urn
        )
        topic = lambda_usecase.lambda_conversation_topics(
            messages=formated_messages,
            has_chats_room=payload.get("has_chats_room"),
            project_uuid=project_uuid,
            contact_urn=contact_urn
        )

        contact_name = payload.get("name")
        resolution_choice_value = ResolutionEntities.convert_resolution_string_to_int(resolution)

        update_data = {
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "has_chats_room": payload.get("has_chats_room"),
            "external_id": payload.get("external_id"),
            "resolution": resolution_choice_value,
            "topic": topic
        }
        
        if contact_name:
            update_data["contact_name"] = contact_name
        
        conversation_queryset.update(**update_data)

        resolution_dto = ResolutionDTO(
            resolution=resolution_choice_value,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            external_id=payload.get("external_id")
        )
        
        # Log when sending unclassified conversations to billing
        if resolution_choice_value == ResolutionEntities.UNCLASSIFIED:
            logger.info(
                f"[Billing] Sending unclassified conversation to billing - "
                f"project_uuid: {project_uuid}, "
                f"contact_urn: {contact_urn}, "
                f"external_id: {payload.get('external_id')}, "
                f"resolution: {resolution_choice_value}"
            )
        
        resolution_message(resolution_dto)

        # Delete messages after processing (instead of updating resolution)
        message_service.clear_message_cache(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid
        )

    except Exception as e:
        project_uuid = payload.get("project_uuid")
        contact_urn = payload.get("contact_urn")
        channel_uuid = payload.get("channel_uuid")
        external_id = payload.get("external_id")
        has_chats_room = payload.get("has_chats_room", False)
        
        # Determine error type for logging
        error_type = "unknown"
        error_message = str(e)
        
        if isinstance(e, ValueError) and "No unclassified messages found" in error_message:
            error_type = "no_messages_found"
            logger.warning(
                f"[Billing] No messages found for conversation - "
                f"project_uuid: {project_uuid}, contact_urn: {contact_urn}, "
                f"channel_uuid: {channel_uuid}, error: {error_message}"
            )
        else:
            logger.error(
                f"[Billing] Error processing conversation - "
                f"project_uuid: {project_uuid}, contact_urn: {contact_urn}, "
                f"channel_uuid: {channel_uuid}, error_type: {type(e).__name__}, "
                f"error: {error_message}"
            )
        
        # Send unclassified to billing in case of error
        try:
            lambda_usecase = LambdaUseCase()
            
            # Send unclassified event to data lake
            event_data = {
                "event_name": "weni_nexus_data",
                "key": "conversation_classification",
                "value_type": "string",
                "value": "Unclassified",
                "metadata": {
                    "human_support": has_chats_room,
                    "error_type": error_type,
                    "error_message": error_message[:500] if error_message else None,  # Limit error message length
                }
            }
            lambda_usecase.send_datalake_event(
                event_data=event_data,
                project_uuid=project_uuid,
                contact_urn=contact_urn
            )
            
            logger.info(
                f"[Billing] Sent unclassified to billing due to error - "
                f"project_uuid: {project_uuid}, contact_urn: {contact_urn}, "
                f"error_type: {error_type}"
            )
            
            # Update conversation in database with Unclassified status if it exists
            try:
                project = Project.objects.get(uuid=project_uuid)
                conversation_queryset = Conversation.objects.filter(
                    project=project,
                    contact_urn=contact_urn,
                    channel_uuid=channel_uuid,
                    resolution=ResolutionEntities.IN_PROGRESS
                )
                
                if conversation_queryset.exists():
                    update_data = {
                        "resolution": ResolutionEntities.UNCLASSIFIED,
                        "start_date": payload.get("start_date"),
                        "end_date": payload.get("end_date"),
                        "has_chats_room": has_chats_room,
                        "external_id": external_id,
                    }
                    
                    contact_name = payload.get("name")
                    if contact_name:
                        update_data["contact_name"] = contact_name
                    
                    conversation_queryset.update(**update_data)
                    
                    # Send resolution message to billing
                    resolution_dto = ResolutionDTO(
                        resolution=ResolutionEntities.UNCLASSIFIED,
                        project_uuid=project_uuid,
                        contact_urn=contact_urn,
                        external_id=external_id
                    )
                    resolution_message(resolution_dto)
                    
                    logger.info(
                        f"[Billing] Updated conversation to Unclassified in database - "
                        f"project_uuid: {project_uuid}, contact_urn: {contact_urn}"
                    )
            except Project.DoesNotExist:
                logger.warning(
                    f"[Billing] Project not found when updating conversation - "
                    f"project_uuid: {project_uuid}, contact_urn: {contact_urn}"
                )
            except Exception as update_error:
                logger.error(
                    f"[Billing] Error updating conversation to Unclassified - "
                    f"project_uuid: {project_uuid}, contact_urn: {contact_urn}, "
                    f"error: {str(update_error)}"
                )
                
        except Exception as billing_error:
            logger.error(
                f"[Billing] Error sending unclassified to billing - "
                f"project_uuid: {project_uuid}, contact_urn: {contact_urn}, "
                f"error: {str(billing_error)}"
            )
        
        # Send exception to Sentry
        sentry_sdk.set_context(
            "conversation_context",
            {
                "payload": payload,
                "error_type": error_type,
                "error_message": error_message
            }
        )
        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_tag("contact_urn", contact_urn)
        sentry_sdk.set_tag("error_type", error_type)
        sentry_sdk.capture_exception(e)
