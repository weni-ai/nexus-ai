import requests

from django.conf import settings

from nexus.internals import InternalAuthentication


class TypingUsecase:

    def send_typing_message(self, contact_urn: str, msg_external_id: str, project_uuid: str):
        if contact_urn.startswith("whatsapp"):
            url = f"{settings.FLOWS_REST_ENDPOINT}/api/v2/internals/whatsapp_broadcasts"

            print(f"[ + Typing Indicator + ] sending request to {url}")

            body = {
                "urns": [contact_urn],
                "project": project_uuid,
                "msg": {
                    "action_external_id": msg_external_id,
                    "action_type": "typing_indicator"
                }
            }

            print(f"[ + Typing Indicator + ] body: {body}")

            internal_auth = InternalAuthentication()
            print(f"[ + DEBUG + ] Sending typing message to {contact_urn} with msg_external_id {msg_external_id}")
            requests.post(url, json=body, headers=internal_auth.headers)
