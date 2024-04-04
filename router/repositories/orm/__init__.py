from __future__ import absolute_import, unicode_literals
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

django.setup()
from typing import List
from dataclasses import dataclass
from router.repositories import Repository

from nexus.intelligences.models import ContentBase
from nexus.projects.models import Project
from nexus.actions.models import Flow
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)
from router.entities import FlowDTO


class ProjectORMRepository(Repository):
    pass
class ContentBaseRepository(Repository):
    def get_instructions(self, content_base_uuid: str):
        content_base = ContentBase.objects.get(uuid=content_base_uuid)


class FlowsORMRepository(Repository):
    pass

    def project_flow_fallback(self, project_uuid: str, fallback: bool) -> FlowDTO:
        content_base = get_default_content_base_by_project(project_uuid)
        flow = Flow.objects.filter(content_base=content_base, fallback=fallback).first()  # o que fazer se o fallback vier vazio??
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