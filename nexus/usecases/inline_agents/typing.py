import logging

from django.conf import settings

from nexus.internals import InternalAuthentication

logger = logging.getLogger(__name__)


class TypingUsecase:
    def __init__(self):
        self.auth_client = InternalAuthentication()

    def send_typing_message(
        self,
        contact_urn: str,
        msg_external_id: str,
        project_uuid: str,
        preview: bool = False,
    ):
        if preview:
            logger.debug("Skipping typing indicator for preview mode")
            return

        url = f"{settings.FLOWS_REST_ENDPOINT}/api/v2/internals/whatsapp_broadcasts"

        body = {
            "urns": [contact_urn],
            "project": project_uuid,
            "msg": {
                "action_external_id": msg_external_id,
                "action_type": "typing_indicator",
            },
        }

        logger.debug(f"Sending typing indicator to {contact_urn}")

        try:
            response = self.auth_client.make_request_with_retry(
                method="POST", url=url, json=body, timeout=10
            )

            if not response.status_code == 200:
                logger.warning(
                    f"Typing indicator failed with status {response.status_code}"
                )
                return

            logger.debug("Typing indicator sent successfully")

        except Exception as e:
            logger.error(f"Failed to send typing indicator: {e}")
