from router.repositories.orm import FlowsORMRepository

from router.classifiers.safe_guard import SafeGuard
from router.classifiers.prompt_guard import PromptGuard
from router.flow_start.interfaces import FlowStart

from router.entities import (
    Message,
    FlowDTO,
)


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
        self.msg_event = msg_event
        self.flow_start = flow_start
        self.user_email = user_email

        self.flow_started = False

    def prompt_guard(self, message: str) -> bool:
        flow_dto = self.flows_repository.get_classifier_flow_by_action_type("prompt_guard")
        if flow_dto:
            prompt_guard = PromptGuard()
            is_safe = prompt_guard.classify(message)
            if is_safe:
                return self.flow_started
            return self.direct_flows(flow_dto)
        return self.flow_started

    def safety_check(self, message: str) -> bool:
        flow_dto = self.flows_repository.get_classifier_flow_by_action_type("safe_guard")
        if flow_dto:
            safeguard = SafeGuard()
            is_safe = safeguard.classify(message)
            if is_safe:
                return self.flow_started
            return self.direct_flows(flow_dto)
        return self.flow_started

    def direct_flows(
        self,
        flow_dto: FlowDTO
    ) -> bool:

        print(f"[+ Pre Classification Direct Flow: {flow_dto.uuid} +]")

        self.flow_start.start_flow(
            flow=flow_dto,
            user=self.user_email,
            urns=[self.message.contact_urn],
            user_message="",
            msg_event=self.msg_event,
        )
        self.flow_started = True
        return self.flow_started

    def pre_classification_route(self) -> bool:
        if self.safety_check(self.message):
            return self.flow_started
        if self.prompt_guard(self.message):
            return self.flow_started
        return self.flow_started
