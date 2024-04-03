from __future__ import absolute_import, unicode_literals
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")

django.setup()
from typing import List
from dataclasses import dataclass
from router.repositories import Repository

from nexus.projects.models import Project
from nexus.actions.models import Flow
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)
from router.entities import FlowDTO


class ProjectORMRepository(Repository):

    def get(self, uuid: str):
        return Project.objects.get(uuid=uuid)

    def get_all(self):
        return Project.objects.all()[::1]
    
    def add(self):
        return super().add()

    def update(self, uuid: str):
        return super().update(uuid)
    
    def delete(self, uuid: str):
        return super().delete(uuid)


class FlowsORMRepository(Repository):
    def get(self, uuid: str):
        return Project.objects.get(uuid=uuid)

    def get_all(self):
        return Project.objects.all()[::1]
    
    def add(self):
        return super().add()

    def update(self, uuid: str):
        return super().update(uuid)
    
    def delete(self, uuid: str):
        return super().delete(uuid)

    def project_flow_fallback(self, project_uuid: str, fallback: bool) -> FlowDTO:
        content_base = get_default_content_base_by_project(project_uuid)
        flow = Flow.objects.filter(content_base=content_base, fallback=fallback).first()
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
                    prompt=flow.prompt
                )
            )
        
        return flows_list