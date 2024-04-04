from nexus.actions.models import Flow
from dataclasses import dataclass
from nexus.usecases.actions.retrieve import RetrieveFlowsUseCase


@dataclass
class UpdateFlowDTO:
    flow_uuid: str
    prompt: str


class UpdateFlowsUseCase():
    def update_flow(self, flow_dto: UpdateFlowDTO) -> Flow:
        flow: Flow = RetrieveFlowsUseCase().retrieve_flow_by_uuid(flow_dto.flow_uuid)

        flow.prompt = flow_dto.prompt
        flow.save(update_fields=["prompt"])
        flow.refresh_from_db()

        return flow
