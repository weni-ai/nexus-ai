from nexus.actions.models import Flow
from dataclasses import dataclass
from nexus.usecases.actions.retrieve import RetrieveFlowsUseCase


@dataclass
class DeleteFlowDTO:
    flow_uuid: str


class DeleteFlowsUseCase():
    def hard_delete_flow(self, flow_dto: DeleteFlowDTO) -> None:
        flow: Flow = RetrieveFlowsUseCase().retrieve_flow_by_uuid(flow_dto.flow_uuid)
        flow.delete()
        return