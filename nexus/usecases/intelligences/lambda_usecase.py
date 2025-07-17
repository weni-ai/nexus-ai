import boto3
import json

from django.conf import settings

from nexus.usecases.inline_agents.create import CreateConversationUseCase
from inline_agents.backends.bedrock.adapter import BedrockDataLakeEventAdapter

class LambdaUseCase():

    def __init__(self):
        
        self.boto_client = boto3.client('lambda', region_name=settings.AWS_BEDROCK_REGION_NAME)
        self.adapter = None

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

    def get_lambda_topics(self, project):
        from nexus.intelligences.models import Topics
        topics = Topics.objects.filter(project=project)
        topics_payload = []

        for topic in topics:
            subtopics_payload = []
            for subtopic in topic.subtopics.all():
                subtopics_payload.append({
                    "subtopic_uuid": subtopic.uuid,
                    "name": subtopic.name,
                    "description": subtopic.description
                })
            topics_payload.append({
                "topic_uuid": topic.uuid,
                "name": topic.name,
                "description": topic.description,
                "subtopics": subtopics_payload
            })

        return topics_payload

    def get_lambda_conversation(self, conversation):
        from nexus.intelligences.models import ConversationMessage
        conversation_payload = {
            "conversation_id": conversation.uuid,
            "messages": []
        }
        conversation_messages = ConversationMessage.objects.get(conversation=conversation)

        for message in conversation_messages:
            conversation_payload["messages"].append({
                "sender": message.message.source,
                "timestamp": message.message.created_at,
                "content": message.message.text
            })
        return conversation_payload

    def send_datalake_event(self, event_data: dict, project_uuid: str, contact_urn: str):
        adapter = self._get_data_lake_event_adapter()
        adapter.to_data_lake_custom_event(
            event_data=event_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn
        )

    def lambda_conversation_resolution(self, conversation):
        lambda_conversation = self.get_lambda_conversation(conversation)
        payload_conversation = {
            "conversation": lambda_conversation
        }

        conversation_resolution = self.invoke_lambda(
            lambda_name="conversation-resolution-metric",
            payload=payload_conversation
        )
        conversation_resolution_response = conversation_resolution.get("body")
        event_data = {
            "event_name": "weni_nexus_data",
            "key": "conversation_classification",
            "value_type": "string",
            "value": conversation_resolution_response.get("result"),
            "metadata": {
                "human_support": conversation.has_chats_room,
                "conversation_id": conversation.uuid,
            }
        }
        self.send_datalake_event(
            event_data=event_data,
            project_uuid=conversation.project.uuid,
            contact_urn=conversation.contact_urn
        )



    def lambda_conversation_topics(self, conversation):

        lambda_topics = self.get_lambda_topics(conversation.project)
        lambda_conversation = self.get_lambda_conversation(conversation)

        payload_topics = {
            "topics": lambda_topics,
            "conversation": lambda_conversation
        }

        conversation_topics = self.invoke_lambda(
            lambda_name="topic_classifier_stg",
            payload=payload_topics
        )

        if conversation_topics.get("topic_uuid") is not "":
            event_data = {
                "event_name": "weni_nexus_data",
                "key": "topics",
                "value_type": "string",
                "value": conversation_topics.get("topic_name"),
                "metadata": {
                    "topic_uuid": conversation_topics.get("topic_uuid"),
                    "subtopic_uuid": conversation_topics.get("subtopic_uuid"),
                    "subtopic": conversation_topics.get("subtopic_name"),
                    "human_support": conversation.has_chats_room,
                    "conversation_id": conversation.uuid,
                }
            }
        else:
            event_data = {
                "event_name": "weni_nexus_data",
                "key": "topics",
                "value_type": "string",
                "value": "bias",
                "metadata": {
                    "topic_uuid": "",
                    "subtopic_uuid": "",
                    "subtopic": "",
                    "human_support": conversation.has_chats_room,
                    "conversation_id": conversation.uuid,
                }
            }

        self.send_datalake_event(
            event_data=event_data,
            project_uuid=conversation.project.uuid,
            contact_urn=conversation.contact_urn
        )

    def create_lambda_conversation(
        self, 
        payload: dict
    ): # deixar esse metodo async
        create_conversation_use_case = CreateConversationUseCase()
        conversation = create_conversation_use_case.create_conversation(payload)

        # self.lambda_conversation_resolution(conversation)
        # self.lambda_conversation_topics(conversation)
