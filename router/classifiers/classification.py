from router.classifiers import classify

from router.flow_start.interfaces import FlowStart
from router.classifiers.interfaces import Classifier

from router.entities import (
    Message,
    FlowDTO,
)

from router.repositories.orm import FlowsORMRepository


class Classification:
    def __init__(
        self,
        flows_repository: FlowsORMRepository,
        message: Message,
        msg_event: dict,
        flow_start: FlowStart,
        user_email: str,

    ):
        self.flows_repository = flows_repository
        self.message = message
        self.msg_event = msg_event
        self.flow_start = flow_start
        self.user_email = user_email

        self.flow_started = False

    def direct_flows(
        self,
        flow_dto: FlowDTO
    ) -> bool:

        print(f"[+ Classification Direct Flow: {flow_dto.uuid} +]")

        self.flow_start.start_flow(
            flow=flow_dto,
            user=self.user_email,
            urns=[self.message.contact_urn],
            user_message="",
            msg_event=self.msg_event,
        )
        self.flow_started = True
        return self.flow_started

    def non_custom_actions(self) -> bool:

        action_type = None
        if 'order' in self.message.metadata:
            action_type = 'whatsapp_cart'
            flow_dto = self.flows_repository.get_classifier_flow_by_action_type(action_type=action_type)
            if flow_dto:
                return self.direct_flows(flow_dto)

        if hasattr(self.message, 'attachments') and self.message.attachments:
            action_type = 'attachment'
            flow_dto = self.flows_repository.get_classifier_flow_by_action_type(action_type=action_type)
            if flow_dto:
                return self.direct_flows(flow_dto)

        return self.flow_started

    def custom_actions(
        self,
        classifier: Classifier,
        language: str
    ) -> str:
        action_type = "custom"
        flow_dto = self.flows_repository.project_flows(
            action_type=action_type,
            fallback=False
        )

        if not flow_dto:
            return "other"

        classification = classify(
            classifier=classifier,
            message=self.message.text,
            flows=flow_dto,
            language=language
        )

        return classification
