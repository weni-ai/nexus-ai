import os
from typing import List

import django
from django.core.cache import cache

from nexus.actions.models import Flow
from nexus.intelligences.models import (
    ContentBase,
    ContentBaseAgent,
)
from nexus.logs.models import MessageLog
from nexus.usecases.actions.retrieve import FlowDoesNotExist
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid
from router.entities import AgentDTO, ContactMessageDTO, ContentBaseDTO, FlowDTO, InstructionDTO, ProjectDTO
from router.repositories import Repository

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

# Only call django.setup() if not already in progress
# This prevents "populate() isn't reentrant" errors when imported during app initialization
try:
    django.setup()
except RuntimeError:
    pass  # Django is already setting up or configured


class ContentBaseORMRepository(Repository):
    def _get_content_base(self, content_base_uuid: str) -> ContentBase:
        return ContentBase.objects.get(uuid=content_base_uuid)

    def get_content_base_by_project(self, project_uuid: str) -> ContentBaseDTO:
        content_base = get_default_content_base_by_project(project_uuid)

        return ContentBaseDTO(
            uuid=str(content_base.uuid),
            title=content_base.title,
            intelligence_uuid=str(content_base.intelligence.uuid),
        )

    def get_agent(self, content_base_uuid: str) -> AgentDTO:
        content_base = ContentBase.objects.get(uuid=content_base_uuid)
        agent: ContentBaseAgent = content_base.agent

        return AgentDTO(
            name=agent.name,
            role=agent.role,
            personality=agent.personality,
            goal=agent.goal,
            content_base_uuid=content_base_uuid,
        )

    def list_instructions(self, content_base_uuid: str) -> List[InstructionDTO]:
        content_base: ContentBase = self._get_content_base(content_base_uuid)

        instructions = content_base.instructions.all()

        instructions_list = []

        for instruction in instructions:
            instructions_list.append(
                InstructionDTO(
                    instruction=instruction.instruction, content_base_uuid=str(instruction.content_base.uuid)
                )
            )

        return instructions_list


class FlowsORMRepository(Repository):
    def __init__(
        self,
        project_uuid: str,
    ):
        self.content_base = get_default_content_base_by_project(project_uuid)
        self.flows = Flow.objects.filter(content_base=self.content_base)

    def get_project_flow_by_name(self, name: str):
        flow = self.flows.filter(name__iexact=name).first()

        if not flow:
            raise FlowDoesNotExist

        return FlowDTO(
            pk=str(flow.uuid),
            uuid=str(flow.flow_uuid),
            name=flow.name,
            prompt=flow.prompt,
            fallback=flow.fallback,
            content_base_uuid=str(flow.content_base.uuid),
            send_to_llm=flow.send_to_llm,
        )

    def project_flow_fallback(self, fallback: bool) -> FlowDTO:
        flow = self.flows.filter(fallback=fallback).first()

        if flow:
            return FlowDTO(
                pk=str(flow.uuid),
                uuid=str(flow.flow_uuid),
                name=flow.name,
                prompt=flow.prompt,
                fallback=flow.fallback,
                content_base_uuid=str(flow.content_base.uuid),
            )

    def project_flows(self, fallback: bool = False, action_type: str = "custom") -> List[FlowDTO]:
        flows = self.flows.filter(fallback=fallback, action_type=action_type)

        flows_list = []
        for flow in flows:
            flows_list.append(
                FlowDTO(
                    pk=str(flow.uuid),
                    uuid=str(flow.flow_uuid),
                    name=flow.name,
                    prompt=flow.prompt,
                    fallback=flow.fallback,
                    content_base_uuid=str(flow.content_base.uuid),
                )
            )

        return flows_list

    def get_classifier_flow_list(
        self,
    ) -> List[FlowDTO]:
        flows = self.flows.exclude(action_type="custom")
        flows_list = []
        for flow in flows:
            flows_list.append(
                FlowDTO(
                    pk=str(flow.uuid),
                    uuid=str(flow.uuid),
                    name=flow.name,
                    prompt=flow.prompt,
                    fallback=flow.fallback,
                    content_base_uuid=str(flow.content_base.uuid),
                )
            )

        return flows_list

    def get_classifier_flow_by_action_type(self, action_type: str) -> FlowDTO:
        flow = self.flows.filter(action_type=action_type).first()

        if flow is None:
            return None

        return FlowDTO(
            pk=str(flow.uuid),
            uuid=str(flow.flow_uuid),
            name=flow.name,
            prompt=flow.prompt,
            fallback=flow.fallback,
            content_base_uuid=str(flow.content_base.uuid),
        )


class MessageLogsRepository(Repository):
    def list_cached_messages(self, project_uuid: str, contact_urn: str):
        cache_key = f"last_5_messages_{project_uuid}_{contact_urn}"
        cache_data: list = cache.get(cache_key)

        if cache_data is None:
            return []

        contact_messages = []
        for message in cache_data:
            contact_messages.append(
                ContactMessageDTO(
                    contact_urn=message["contact_urn"],
                    text=message["text"],
                    llm_respose=message["llm_respose"],
                    content_base_uuid=message["content_base_uuid"],
                    project_uuid=message["project_uuid"],
                )
            )

        return contact_messages

    def list_last_messages(self, project_uuid: str, contact_urn: str, number_of_messages: int):
        content_base = get_default_content_base_by_project(project_uuid)
        contact_messages = []
        messages = MessageLog.objects.filter(
            message__contact_urn=contact_urn, content_base=content_base, message__status="S", classification="other"
        ).order_by("-message__created_at")[:number_of_messages]

        messages = list(messages)[::-1]

        for message in messages:
            contact_messages.append(
                ContactMessageDTO(
                    contact_urn=message.message.contact_urn,
                    text=message.message.text,
                    llm_respose=message.llm_response,
                    content_base_uuid=str(message.content_base.uuid),
                    project_uuid=project_uuid,
                )
            )

        return contact_messages


class ProjectORMRepository(Repository):
    def get_project(self, project_uuid) -> ProjectDTO:
        project = get_project_by_uuid(project_uuid)
        return ProjectDTO(uuid=str(project.uuid), name=project.name, indexer_database=project.indexer_database)
