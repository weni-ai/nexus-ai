from nexus.actions.models import Flow
from django.db.models import QuerySet


from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)


class ListFlowsUseCase():
    def list_flow_by_content_base_uuid(self, content_base_uuid: str) -> QuerySet[Flow]:
        return Flow.objects.filter(content_base__uuid=content_base_uuid)
    
    def list_flows_by_project_uuid(self, project_uuid: str) -> QuerySet[Flow]:
        content_base = get_default_content_base_by_project(project_uuid)
        return self.list_flow_by_content_base_uuid(str(content_base.uuid))
