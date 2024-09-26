from dataclasses import dataclass

from nexus.events import event_manager
from nexus.actions.models import TemplateAction
from nexus.usecases.actions.retrieve import RetrieveFlowsUseCase


@dataclass
class DeleteFlowDTO:
    flow_uuid: str


class DeleteFlowsUseCase():
    def __init__(
        self,
        event_manager_notify=event_manager.notify
    ) -> None:
        self.event_manager_notify = event_manager_notify

    def hard_delete_flow(
        self,
        project,
        flow_dto: DeleteFlowDTO,
        user=None,
    ) -> None:
        retrieve_usecase = RetrieveFlowsUseCase()
        flow = retrieve_usecase.retrieve_flow_by_uuid(flow_dto.flow_uuid)

        self.event_manager_notify(
            event="action_activity",
            action=flow,
            action_type="D",
            user=user,
            project=project
        )

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
