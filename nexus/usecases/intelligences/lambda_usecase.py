import boto3
import json

from django.conf import settings

from nexus.usecases.inline_agents.create import CreateConversationUseCase
from nexus.intelligences.models import Topics, Conversation, ConversationMessage


class LambdaUseCase():

    def __init__(self):
        self.boto_client = boto3.client('lambda', region_name=settings.AWS_BEDROCK_REGION_NAME)

    def invoke_lambda(self, lambda_name: str, payload: dict):
        response = self.boto_client.invoke(
            FunctionName=lambda_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        return response

    def get_lambda_topics(self, project):
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


    def create_lambda_conversation(self, payload: dict):

        create_conversation_use_case = CreateConversationUseCase()
        conversation = create_conversation_use_case.create_conversation(payload)

        lambda_topics = self.get_lambda_topics(conversation.project)
        lambda_conversation = self.get_lambda_conversation(conversation)

        if not conversation:
            return

        payload_conversation = {
            "conversation": lambda_conversation
        }

        conversation_resolution = self.invoke_lambda(
            lambda_name="conversation-resolution",
            payload=payload_conversation
        )

        payload_topics = {
            "topics": lambda_topics,
            "conversation": lambda_conversation
        }

        conversation_topics = self.invoke_lambda(
            lambda_name="conversation-topics",
            payload=payload_topics
        )

        # chamar o datalake


