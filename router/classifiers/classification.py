import logging

from router.classifiers import classify
from router.classifiers.interfaces import Classifier
from router.entities import (
    FlowDTO,
    Message,
)
from router.flow_start.interfaces import FlowStart
from router.repositories.orm import FlowsORMRepository

logger = logging.getLogger(__name__)


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
        flow_dto: FlowDTO,
        start_flow: bool,
        user_message: str = None,
        attachments: list = None,
    ):
        logger.info("Classification Direct Flow", extra={"uuid": flow_dto.uuid})

        if start_flow:
            self.flow_start.start_flow(
                flow=flow_dto,
                user=self.user_email,
                urns=[self.message.contact_urn],
                user_message=user_message,
                msg_event=self.msg_event,
                attachments=attachments,
            )
            self.flow_started = True
            return self.flow_started
        return flow_dto

    def non_custom_actions_route(
        self,
        start_flow=True,
    ) -> bool:
        action_type = None
        if "order" in self.message.metadata:
            action_type = "whatsapp_cart"
            flow_dto = self.flows_repository.get_classifier_flow_by_action_type(action_type=action_type)
            if flow_dto:
                return self.direct_flows(flow_dto=flow_dto, start_flow=start_flow)

        if hasattr(self.message, "attachments") and self.message.attachments:
            action_type = "attachment"
            flow_dto = self.flows_repository.get_classifier_flow_by_action_type(action_type=action_type)
            if flow_dto:
                return self.direct_flows(
                    flow_dto=flow_dto, start_flow=start_flow, attachments=self.message.attachments, user_message=""
                )

        return self.flow_started

    def non_custom_actions_preview(
        self,
    ) -> bool:
        if not self.message.text:
            action_type = None
            if "order" in self.message.metadata:
                action_type = "whatsapp_cart"
                flow_dto = self.flows_repository.get_classifier_flow_by_action_type(action_type=action_type)
                if flow_dto:
                    return {"type": "flowstart", "uuid": flow_dto.uuid, "name": flow_dto.name, "msg_event": None}

            if hasattr(self.message, "attachments") and self.message.attachments:
                action_type = "attachment"
                flow_dto = self.flows_repository.get_classifier_flow_by_action_type(action_type=action_type)
                if flow_dto:
                    return {"type": "flowstart", "uuid": flow_dto.uuid, "name": flow_dto.name, "msg_event": None}
                return {
                    "type": "media_and_location_unavailable",
                }

        return self.flow_started

    def non_custom_actions(
        self,
        source: str,
    ):
        if source == "preview":
            return self.non_custom_actions_preview()
        return self.non_custom_actions_route()

    def custom_actions(self, classifier: Classifier, language: str) -> str:
        action_type = "custom"
        flow_dto = self.flows_repository.project_flows(action_type=action_type, fallback=False)

        if not flow_dto:
            return "other"

        classification = classify(classifier=classifier, message=self.message.text, flows=flow_dto, language=language)

        return classification
