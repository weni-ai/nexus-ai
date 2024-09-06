from nexus.actions.models import Flow, TemplateAction
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


def delete_template_action(template_action_uuid: str) -> bool:
    try:
        template_action: TemplateAction = TemplateAction.objects.get(uuid=template_action_uuid)
        template_action.delete()
        return True
    except TemplateAction.DoesNotExist:
        raise ValueError("Template action not found")
    except Exception as e:
        print("Error deleting template action: ", e)
        raise Exception("Error deleting template action")
