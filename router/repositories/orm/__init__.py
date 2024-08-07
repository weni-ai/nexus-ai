from __future__ import absolute_import, unicode_literals
import os
import django

from typing import List
from dataclasses import dataclass

from nexus.intelligences.models import (
    ContentBase,
    ContentBaseAgent,
)
from nexus.actions.models import Flow
from nexus.logs.models import Message, MessageLog
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)

from router.repositories import Repository
from router.entities import (
    AgentDTO,
    FlowDTO,
    InstructionDTO,
    ContentBaseDTO,
    ContactMessageDTO,
)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

django.setup()


class ContentBaseORMRepository(Repository):
    def _get_content_base(self, content_base_uuid: str) -> ContentBase:
        return ContentBase.objects.get(uuid=content_base_uuid)

    def get_content_base_by_project(self, project_uuid: str) -> ContentBase:

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
            content_base_uuid=content_base_uuid
        )

    def list_instructions(self, content_base_uuid: str) -> List[InstructionDTO]:
        content_base: ContentBase = self._get_content_base(content_base_uuid)

        instructions = content_base.instructions.all()

        instructions_list = []

        for instruction in instructions:
            instructions_list.append(
                InstructionDTO(
                    instruction=instruction.instruction,
                    content_base_uuid=str(instruction.content_base.uuid)
                )
            )

        return instructions_list


class FlowsORMRepository(Repository):
    def get_project_flow_by_name(self, project_uuid: str, name: str):
        content_base = get_default_content_base_by_project(project_uuid)
        flow = Flow.objects.filter(content_base=content_base, name=name).first()
        return FlowDTO(
            uuid=str(flow.uuid),
            name=flow.name,
            prompt=flow.prompt,
            fallback=flow.fallback,
            content_base_uuid=str(flow.content_base.uuid)
        )

    def project_flow_fallback(self, project_uuid: str, fallback: bool) -> FlowDTO:
        content_base = get_default_content_base_by_project(project_uuid)
        flow = Flow.objects.filter(content_base=content_base, fallback=fallback).first()  # TODO: Flow.DoesNotExist
        if flow:
            return FlowDTO(
                uuid=str(flow.uuid),
                name=flow.name,
                prompt=flow.prompt,
                fallback=flow.fallback,
                content_base_uuid=str(flow.content_base.uuid)
            )

    def project_flows(self, project_uuid: str, fallback: bool = False) -> List[FlowDTO]:
        content_base = get_default_content_base_by_project(project_uuid)
        flows = Flow.objects.filter(content_base=content_base, fallback=fallback)

        flows_list = []
        for flow in flows:
            flows_list.append(
                FlowDTO(
                    uuid=str(flow.uuid),
                    name=flow.name,
                    prompt=flow.prompt,
                    fallback=flow.fallback,
                    content_base_uuid=str(flow.content_base.uuid)
                )
            )

        return flows_list


class MessageLogsRepository(Repository):
    def list_last_messages(self, project_uuid: str, contact_urn: str, number_of_messages: int) -> List[ContactMessageDTO]:
        content_base = get_default_content_base_by_project(project_uuid)
        contact_messages = []
        messages = Message.objects.filter(
            contact_urn=contact_urn,
            messagelog__content_base=content_base,
            status="S"
        ).order_by("-created_at")[:number_of_messages]
        for message in messages:

            message_log: MessageLog = message.messagelog

            contact_messages.append(
                ContactMessageDTO(
                    contact_urn=message.contact_urn,
                    text=message.text,
                    llm_respose=message_log.llm_response,
                    content_base_uuid=str(message_log.content_base.uuid),
                    project_uuid=project_uuid
                )
            )
        return contact_messages
