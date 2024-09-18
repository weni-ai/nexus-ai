from dataclasses import dataclass

from nexus.events import event_manager

from django.forms.models import model_to_dict

from nexus.usecases.actions.retrieve import RetrieveFlowsUseCase
from nexus.actions.models import Flow, TemplateAction
from nexus.users.models import User


@dataclass
class UpdateFlowDTO:
    flow_uuid: str
    prompt: str = None
    name: str = None

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class UpdateTemplateActionDTO:
    template_action_uuid: str
    name: str = None
    prompt: str = None
    action_type: str = None
    group: str = None
    display_prompt: str = None

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


class UpdateFlowsUseCase():

    def __init__(
        self,
        event_manager_notify=event_manager.notify
    ) -> None:
        self.event_manager_notify = event_manager_notify

    def _save_log(
        self,
        user,
        action: Flow,
        values_before_update: dict,
        values_after_update: dict
    ) -> bool:

        self.event_manager_notify(
            event="action_activity",
            action_type="U",
            action=action,
            values_before_update=values_before_update,
            values_after_update=values_after_update,
            user=user
        )

    def update_flow(
        self,
        flow_dto: UpdateFlowDTO,
        user: User = None,
    ) -> Flow:
        flow: Flow = RetrieveFlowsUseCase().retrieve_flow_by_uuid(flow_dto.flow_uuid)

        values_before_update = model_to_dict(flow)
        for attr, value in flow_dto.dict().items():
            setattr(flow, attr, value)
        flow.save()
        values_after_update = model_to_dict(flow)

        if user:
            self._save_log(
                action=flow,
                values_before_update=values_before_update,
                values_after_update=values_after_update,
                user=user
            )

        return flow


class UpdateTemplateActionUseCase():

    def update_template_action(
        self,
        template_action_dto: UpdateTemplateActionDTO
    ) -> TemplateAction:
        try:
            template_action = TemplateAction.objects.get(
                uuid=template_action_dto.template_action_uuid
            )

            for attr, value in template_action_dto.dict().items():
                setattr(template_action, attr, value)
            template_action.save()

            return template_action
        except TemplateAction.DoesNotExist:
            raise ValueError("Template action not found")
        except Exception as e:
            print("Error updating template action: ", e)
            raise Exception("Error updating template action")
