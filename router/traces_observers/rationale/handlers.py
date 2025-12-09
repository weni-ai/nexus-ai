"""
Handler classes for different rationale processing scenarios.

This module extracts complex logic from RationaleObserver to reduce cyclomatic complexity.
"""

import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class RationaleMessageSender:
    """Handles sending rationale messages and typing indicators."""

    def __init__(self, typing_usecase, flows_user_email: str):
        self.typing_usecase = typing_usecase
        self.flows_user_email = flows_user_email

    def send_typing_if_needed(
        self, message_external_id: str, contact_urn: str, project_uuid: str, preview: bool
    ) -> None:
        """Send typing indicator if message_external_id is provided."""
        if not message_external_id:
            return

        self.typing_usecase.send_typing_message(
            contact_urn=contact_urn,
            msg_external_id=message_external_id,
            project_uuid=project_uuid,
            preview=preview,
        )

    def send_rationale_message(
        self,
        text: str,
        contact_urn: str,
        project_uuid: str,
        session_id: str,
        contact_name: str,
        send_message_callback: Callable,
        channel_uuid: Optional[str] = None,
    ) -> None:
        """Send rationale message and save to database."""
        from router.traces_observers.save_traces import save_inline_message_to_database

        try:
            send_message_callback(
                text=text,
                urns=[contact_urn],
                project_uuid=project_uuid,
                user=self.flows_user_email,
            )
            save_inline_message_to_database(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                text=text,
                preview=False,
                session_id=session_id,
                source_type="agent",
                contact_name=contact_name,
                channel_uuid=channel_uuid,
            )
        except Exception as e:
            logger.error(f"Error sending rationale message: {str(e)}", exc_info=True)


class RationaleTextImprover:
    """Handles improving rationale text using Bedrock."""

    def __init__(self, bedrock_client, model_id: str):
        self.bedrock_client = bedrock_client
        self.model_id = model_id

    def improve_first_rationale(self, rationale_text: str, user_input: str = "") -> str:
        """Improve first rationale text."""
        from django.conf import settings

        try:
            instruction_content = settings.RATIONALE_IMPROVEMENT_INSTRUCTIONS

            if user_input:
                instruction_content += (
                    f"\n                    <user_message>{user_input}</user_message>\n                "
                )

            instruction_content += f"\n                <thought>{rationale_text}</thought>\n            "

            conversation = [{"role": "user", "content": [{"text": instruction_content}]}]

            response = self.bedrock_client.converse(
                modelId=self.model_id,
                messages=conversation,
                inferenceConfig={"maxTokens": 150, "temperature": 0},
            )

            logger.debug(f"Improvement Response: {response}")
            response_text = response["output"]["message"]["content"][0]["text"]

            if response_text.strip().lower() == "invalid":
                return "Processando sua solicitação agora."

            return response_text.strip().strip("\"'")
        except Exception as e:
            logger.error(f"Error improving rationale text: {str(e)}", exc_info=True)
            return rationale_text

    def improve_subsequent_rationale(
        self, rationale_text: str, previous_rationales: Optional[list] = None, user_input: str = ""
    ) -> str:
        """Improve subsequent rationale text."""
        from django.conf import settings

        if previous_rationales is None:
            previous_rationales = []

        try:
            instruction_content = settings.SUBSEQUENT_RATIONALE_INSTRUCTIONS

            if user_input:
                instruction_content += f"<user_message>{user_input}</user_message>"

            if previous_rationales:
                instruction_content += f"""
                <previous_thought>
                {' '.join([f"- {r}" for r in previous_rationales])}
                </previous_thought>
                """

            instruction_content += f"<main_thought>{rationale_text}</main_thought>"

            conversation = [{"role": "user", "content": [{"text": instruction_content}]}]

            response = self.bedrock_client.converse(
                modelId=self.model_id, messages=conversation, inferenceConfig={"maxTokens": 150, "temperature": 0}
            )

            response_text = response["output"]["message"]["content"][0]["text"]
            return response_text.strip().strip("\"'")
        except Exception as e:
            logger.error(f"Error improving subsequent rationale text: {str(e)}", exc_info=True)
            return rationale_text


class RationaleValidator:
    """Validates rationale text."""

    @staticmethod
    def is_valid(rationale_text: str) -> bool:
        """Check if rationale text is valid."""
        import unicodedata

        text = rationale_text.lower()
        text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
        return not text.startswith("invalid")


class RationaleHandler:
    """Base handler for rationale processing scenarios."""

    def __init__(
        self,
        message_sender: RationaleMessageSender,
        text_improver: RationaleTextImprover,
        validator: RationaleValidator,
        redis_task_manager,
    ):
        self.message_sender = message_sender
        self.text_improver = text_improver
        self.validator = validator
        self.redis_task_manager = redis_task_manager

    def handle(self, rationale_text: str, context, session_data: Dict) -> None:
        """Handle rationale processing. Must be implemented by subclasses."""
        raise NotImplementedError


class FirstRationaleHandler(RationaleHandler):
    """Handles first rationale with agent scenario."""

    def handle(self, rationale_text: str, context, session_data: Dict) -> None:
        """Handle first rationale when agent is called."""
        self.message_sender.send_typing_if_needed(
            context.message_external_id, context.contact_urn, context.project_uuid, context.preview
        )

        improved_text = self.text_improver.improve_first_rationale(rationale_text, context.user_input)
        self.message_sender.send_typing_if_needed(
            context.message_external_id, context.contact_urn, context.project_uuid, context.preview
        )

        if self.validator.is_valid(improved_text):
            session_data["rationale_history"].append(improved_text)
            self.message_sender.send_typing_if_needed(
                context.message_external_id, context.contact_urn, context.project_uuid, context.preview
            )
            self.message_sender.send_rationale_message(
                text=improved_text,
                contact_urn=context.contact_urn,
                project_uuid=context.project_uuid,
                session_id=context.session_id,
                contact_name=context.contact_name,
                send_message_callback=context.send_message_callback,
                channel_uuid=context.channel_uuid,
            )
            self.message_sender.send_typing_if_needed(
                context.message_external_id, context.contact_urn, context.project_uuid, context.preview
            )

        self.message_sender.send_typing_if_needed(
            context.message_external_id, context.contact_urn, context.project_uuid, context.preview
        )
        session_data["is_first_rationale"] = False
        self.redis_task_manager.save_rationale_session_data(context.session_id, session_data)


class SubsequentRationaleHandler(RationaleHandler):
    """Handles subsequent rationale scenario."""

    def handle(self, rationale_text: str, context, session_data: Dict) -> None:
        """Handle subsequent rationale."""
        improved_text = self.text_improver.improve_subsequent_rationale(
            rationale_text=rationale_text,
            previous_rationales=session_data.get("rationale_history", []),
            user_input=context.user_input,
        )

        if not self.validator.is_valid(improved_text):
            return

        session_data.setdefault("rationale_history", []).append(improved_text)
        self.redis_task_manager.save_rationale_session_data(context.session_id, session_data)

        self.message_sender.send_typing_if_needed(
            context.message_external_id, context.contact_urn, context.project_uuid, context.preview
        )

        self.message_sender.send_rationale_message(
            text=improved_text,
            contact_urn=context.contact_urn,
            project_uuid=context.project_uuid,
            session_id=context.session_id,
            contact_name=context.contact_name,
            send_message_callback=context.send_message_callback,
            channel_uuid=context.channel_uuid,
        )

        self.message_sender.send_typing_if_needed(
            context.message_external_id, context.contact_urn, context.project_uuid, context.preview
        )
