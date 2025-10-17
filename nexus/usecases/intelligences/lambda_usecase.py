import boto3
import json
import sentry_sdk

from django.conf import settings

from nexus.intelligences.models import Conversation
from nexus.celery import app as celery_app
from nexus.projects.models import Project
from nexus.intelligences.producer.resolution_producer import ResolutionDTO, resolution_message

from router.services.message_service import MessageService
from router.repositories.entities import ResolutionEntities

from inline_agents.backends.bedrock.adapter import BedrockDataLakeEventAdapter


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
        lambda_usecase = LambdaUseCase()
        message_service = lambda_usecase._get_message_service()

        # Use new conversation-based message retrieval
        messages = message_service.get_messages_for_conversation(
            project_uuid=payload.get("project_uuid"),
            contact_urn=payload.get("contact_urn"),
            channel_uuid=payload.get("channel_uuid"),
            # If any errors happen to an older conversation, we will get all messages for correct conversation
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
        )

        if not messages:
            raise ValueError("No unclassified messages found for conversation period")

        project = Project.objects.get(uuid=payload.get("project_uuid"))
        conversation_queryset = Conversation.objects.filter(
            project=project,
            contact_urn=payload.get("contact_urn"),
            channel_uuid=payload.get("channel_uuid"),
            resolution=ResolutionEntities.IN_PROGRESS
        )

        formated_messages = lambda_usecase.get_lambda_conversation(messages)
        resolution = lambda_usecase.lambda_conversation_resolution(
            messages=formated_messages,
            has_chats_room=payload.get("has_chats_room"),
            project_uuid=payload.get("project_uuid"),
            contact_urn=payload.get("contact_urn")
        )
        topic = lambda_usecase.lambda_conversation_topics(
            messages=formated_messages,
            has_chats_room=payload.get("has_chats_room"),
            project_uuid=payload.get("project_uuid"),
            contact_urn=payload.get("contact_urn")
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
            project_uuid=payload.get("project_uuid"),
            contact_urn=payload.get("contact_urn"),
            external_id=payload.get("external_id")
        )
        resolution_message(resolution_dto)

        # Delete messages after processing (instead of updating resolution)
        message_service.clear_message_cache(
            project_uuid=payload.get("project_uuid"),
            contact_urn=payload.get("contact_urn"),
            channel_uuid=payload.get("channel_uuid")
        )

    except Exception as e:
        sentry_sdk.set_context(
            "conversation_context",
            {
                "payload": payload
            }
        )
        sentry_sdk.set_tag("project_uuid", payload.get("project_uuid"))
        sentry_sdk.set_tag("contact_urn", payload.get("contact_urn"))
        sentry_sdk.capture_exception(e)
