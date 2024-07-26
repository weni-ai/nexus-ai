from nexus.actions.models import Flow
from dataclasses import dataclass
from nexus.usecases.actions.retrieve import RetrieveFlowsUseCase


@dataclass
class UpdateFlowDTO:
    flow_uuid: str
    prompt: str | None
    name: str | None


class UpdateFlowsUseCase():
    def update_flow(self, flow_dto: UpdateFlowDTO) -> Flow:
        flow: Flow = RetrieveFlowsUseCase().retrieve_flow_by_uuid(flow_dto.flow_uuid)
        update_fields = []

        if flow_dto.prompt:
            flow.prompt = flow_dto.prompt
            update_fields.append("prompt")

        if flow_dto.name:
            flow.name = flow_dto.name
            update_fields.append("name")

        flow.save(update_fields=update_fields)
        flow.refresh_from_db()

        return flow
