from typing import Dict, List

from django.db.models import QuerySet

from nexus.actions.models import Flow, TemplateAction
from nexus.internals.flows import FlowsRESTClient, RestClient


from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)


class ListFlowsUseCase:

    def __init__(self, client: RestClient = FlowsRESTClient()) -> None:
        self.rest_client = client

    def list_flow_by_content_base_uuid(self, content_base_uuid: str) -> QuerySet[Flow]:
        return Flow.objects.filter(content_base__uuid=content_base_uuid)

    def list_flows_by_project_uuid(self, project_uuid: str) -> QuerySet[Flow]:
        content_base = get_default_content_base_by_project(project_uuid)
        return self.list_flow_by_content_base_uuid(str(content_base.uuid))

    def search_flows_by_project(self, project_uuid: str, name: str = None, page_size: int = 20, page: int = 1) -> Dict:

        if name:
            data: List = self.rest_client.get_project_flows(project_uuid, name)
            return {'count': len(data), 'next': None, 'previous': None, 'results': data}

        data: Dict = self.rest_client.list_project_flows(project_uuid, page_size, page)

        return data


class ListTemplateActionUseCase:

    def list_template_action(self):
        return TemplateAction.objects.all()
