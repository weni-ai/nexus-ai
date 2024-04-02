from dataclasses import dataclass

from nexus.actions.models import Flow
from django.db.models import QuerySet

from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)

@dataclass
class CreateFlowDTO:
    project_uuid: str
    flow_uuid: str
    name: str
    prompt: str
    fallback: bool = False


class CreateFlowsUseCase():
    def create_flow(self, create_dto: CreateFlowDTO) -> Flow:

        content_base = get_default_content_base_by_project(create_dto.project_uuid)
        
        return Flow.objects.create(
            uuid=create_dto.flow_uuid,
            name=create_dto.name,
            prompt=create_dto.prompt,
            fallback=create_dto.fallback,
            content_base=content_base
        )