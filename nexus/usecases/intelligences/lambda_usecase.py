import boto3
import json

from django.conf import settings

from nexus.intelligences.models import Conversation
from nexus.celery import app as celery_app
from nexus.projects.models import Project
from router.tasks.redis_task_manager import RedisTaskManager
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
            lambda_name=str(settings.AWS_COMPONENTS_FUNCTION_ARN),
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

    def _get_task_manager(self):
        if self.task_manager is None:
            self.task_manager = RedisTaskManager()
        return self.task_manager

    def _convert_resolution_to_choice_value(self, resolution_string: str) -> str:

        resolution_mapping = {
            "resolved": "0",
            "unresolved": "1",
            "in progress": "2"
        }
        return resolution_mapping.get(resolution_string.lower(), "2")  # Default to "2" (In Progress)

    def lambda_component_parser(
        self,
        final_response: str,
        use_components: bool
    ) -> str:
        print("=" * 10, "COMPONENT_PARSER_START", "=" * 10)
        print(f"Final Response: {final_response}")
        print(f"Use Components: {use_components}")

        if not use_components:
            return final_response

        prompt_type = "POST_PROCESSING"
        data = {
            "invokeModelRawResponse": f"<final_response>{final_response}</final_response>",
            "promptType": prompt_type,
        }
        print(f"Data: {data}")
        response = self.invoke_lambda(
            lambda_name=str(settings.AWS_COMPONENTS_FUNCTION_ARN),
            payload=data
        )
        print(f"Response: {response}")
        response = json.loads(response.get("Payload").read())
        print(f"Response Payload: {response}")
        parsed_final_response = response.get("postProcessingParsedResponse").get("responseText")
        print(f"Parsed Final Response: {parsed_final_response}")
        print("=" * 10, "COMPONENT_PARSER_END", "=" * 10)
        return parsed_final_response

@celery_app.task
def create_lambda_conversation(
    payload: dict,
):
    if payload.get("project_uuid") not in settings.CUSTOM_LAMBDA_CONVERSATION_PROJECTS:
        return

    lambda_usecase = LambdaUseCase()
    task_manager = lambda_usecase._get_task_manager()
    messages = task_manager.get_cache_messages(
        project_uuid=payload.get("project_uuid"),
        contact_urn=payload.get("contact_urn")
    )

    if not messages:
        return

    try:
        project = Project.objects.get(uuid=payload.get("project_uuid"))
        conversation_queryset = Conversation.objects.filter(
            project=project,
            contact_urn=payload.get("contact_urn"),
            start_date__gte=payload.get("start_date"),
            start_date__lte=payload.get("end_date"),
            channel_uuid=payload.get("channel_uuid")
        )
    except Conversation.DoesNotExist:
        return

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

    resolution_choice_value = lambda_usecase._convert_resolution_to_choice_value(resolution)

    update_data = {
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "has_chats_room": payload.get("has_chats_room"),
        "contact_name": payload.get("name"),
        "contact_urn": payload.get("contact_urn"),
        "external_id": payload.get("external_id"),
        "resolution": resolution_choice_value,
        "topic": topic
    }

    conversation_queryset.update(**update_data)

    task_manager.clear_message_cache(
        project_uuid=payload.get("project_uuid"),
        contact_urn=payload.get("contact_urn")
    )
