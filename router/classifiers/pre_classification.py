from router.classifiers.prompt_guard import PromptGuard
from router.classifiers.safe_guard import SafeGuard
from router.entities import (
    FlowDTO,
    Message,
)
from router.flow_start.interfaces import FlowStart
from router.repositories.orm import FlowsORMRepository


class PreClassification:
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
        self.message_text = message.text
        self.msg_event = msg_event
        self.flow_start = flow_start
        self.user_email = user_email

        self.flow_started = False

    def prompt_guard(self, start_flow: bool) -> bool:
        flow_dto = self.flows_repository.get_classifier_flow_by_action_type("prompt_guard")
        if flow_dto:
            prompt_guard = PromptGuard()
            is_safe = prompt_guard.classify(self.message_text)
            if is_safe:
                return self.flow_started
            return self.direct_flows(flow_dto=flow_dto, start_flow=start_flow)
        return self.flow_started

    def safety_check(self, start_flow: bool) -> bool:
        flow_dto = self.flows_repository.get_classifier_flow_by_action_type("safe_guard")
        if flow_dto:
            safeguard = SafeGuard()
            is_safe = safeguard.classify(self.message_text)
            if is_safe:
                return self.flow_started
            return self.direct_flows(flow_dto=flow_dto, start_flow=start_flow)
        return self.flow_started

    def direct_flows(self, flow_dto: FlowDTO, start_flow: bool):
        import logging

        logging.getLogger(__name__).info("Pre Classification Direct Flow", extra={"uuid": flow_dto.uuid})

        if start_flow:
            self.flow_start.start_flow(
                flow=flow_dto,
                user=self.user_email,
                urns=[self.message.contact_urn],
                user_message="",
                msg_event=self.msg_event,
            )
            self.flow_started = True
            return self.flow_started
        return flow_dto

    def pre_classification_route(self) -> bool:
        if self.message_text:
            if self.safety_check(start_flow=True):
                return self.flow_started
            if self.prompt_guard(start_flow=True):
                return self.flow_started
        return self.flow_started

    def pre_classification_preview(self) -> dict:
        import logging

        logging.getLogger(__name__).info("Pre Classification Preview", extra={"message": str(self.message)})

        if self.message_text:
            flow_dto = self.safety_check(start_flow=False)
            if flow_dto:
                return {"type": "flowstart", "uuid": flow_dto.uuid, "name": flow_dto.name, "msg_event": None}

            flow_dto = self.prompt_guard(start_flow=False)
            if flow_dto:
                return {"type": "flowstart", "uuid": flow_dto.uuid, "name": flow_dto.name, "msg_event": None}

        return {}

    def pre_classification(self, source: str):
        if source == "preview":
            return self.pre_classification_preview()
        return self.pre_classification_route()
