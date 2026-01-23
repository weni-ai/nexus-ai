import json
from typing import Callable, Dict, List

import sentry_sdk

from router.clients.flows.http.send_message import WhatsAppBroadcastHTTPClient
from router.direct_message import DirectMessage


class SimulateBroadcast(DirectMessage):
    def __init__(self, host: str, access_token: str, get_file_info: Callable) -> None:
        self.__host = host
        self.__access_token = access_token
        self.get_file_info = get_file_info

    def send_direct_message(
        self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict], **kwargs
    ) -> None:
        sources: List[Dict] = []
        seen_uuid: List[str] = []

        for chunk in full_chunks:
            file_uuid = chunk.get("file_uuid")

            if file_uuid in seen_uuid:
                continue

            seen_uuid.append(file_uuid)

            file_info = self.get_file_info(file_uuid)

            if file_info:
                sources.append(
                    {
                        "filename": file_info.get("filename"),
                        "uuid": file_uuid,
                        "created_file_name": file_info.get("created_file_name"),
                        "extension_file": file_info.get("extension_file"),
                    }
                )

        response_data = {"type": "broadcast", "message": text, "fonts": sources}

        return response_data


class SimulateWhatsAppBroadcastHTTPClient(WhatsAppBroadcastHTTPClient):
    def send_direct_message(
        self,
        msg: Dict,
        urns: List,
        project_uuid: str,
        user: str,
        full_chunks: List[Dict] = None,
        backend: str = "BedrockBackend",
        **kwargs,
    ) -> None:
        if backend == "BedrockBackend":
            return self.format_response_for_bedrock(msg, urns, project_uuid, user, full_chunks)

        return self.format_message_for_openai(msg, urns, project_uuid, user, full_chunks)

    def format_response_for_bedrock(
        self, msg: Dict, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]
    ) -> Dict:
        msgs = self.get_json_strings(msg)
        if not msgs:
            msgs = [{"msg": {"text": str(msg)}}]
        response_data = {"type": "broadcast", "message": msgs, "fonts": []}

        return response_data

    def format_message_for_openai(
        self, msg: Dict, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]
    ) -> Dict:
        try:
            msg = json.loads(msg)
        except Exception as error:
            sentry_context = {
                "message": msg,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "project_uuid": project_uuid,
                "preview": True,
            }
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_context("session_error", sentry_context)
            sentry_sdk.capture_exception(error)
        return {"type": "broadcast", "message": msg, "fonts": []}
