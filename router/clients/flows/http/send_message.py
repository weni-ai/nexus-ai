import ast
import json
import logging
import re
from typing import Dict, List

import requests

from nexus.internals.flows import FlowsRESTClient
from router.direct_message import DirectMessage, exceptions
from router.entities.mailroom import extract_ig_comment_broadcast_fields

logger = logging.getLogger(__name__)


def ig_comment_fields_from_kwargs(kwargs: Dict) -> Dict[str, str]:
    """Prefer explicit kwargs from dispatch; fall back to message metadata."""
    if "ig_comment_id" in kwargs:
        fields = {"ig_comment_id": kwargs["ig_comment_id"]}
        if "ig_response_type" in kwargs:
            fields["ig_response_type"] = kwargs["ig_response_type"]
        return fields
    return extract_ig_comment_broadcast_fields(kwargs.get("metadata"))


def apply_ig_comment_fields_to_broadcast_msgs(msgs: List, ig_fields: Dict[str, str]) -> List:
    if not ig_fields:
        return msgs
    for item in msgs:
        if isinstance(item, dict) and isinstance(item.get("msg"), dict):
            item["msg"].update(ig_fields)
    return msgs


class SendMessageHTTPClient(DirectMessage):
    def __init__(self, host: str, access_token: str, use_grpc: bool = False) -> None:
        self.__host = host
        self.__access_token = access_token
        self.__use_grpc = use_grpc

    def send_direct_message(
        self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict], **kwargs
    ) -> None:
        if self.__use_grpc:
            # Use same format as whatsapp_broadcasts endpoint
            msg = {"msg": {"text": text}}
            channel_uuid = kwargs.get("channel_uuid", "")
            logger.info(
                f"[SendMessageHTTPClient] Using GRPC stream endpoint - "
                f"project: {project_uuid}, urns: {urns}, channel_uuid: {channel_uuid}"
            )
            response = FlowsRESTClient().whatsapp_broadcast(
                urns, msg, project_uuid, use_stream=True, channel_uuid=channel_uuid
            )
            try:
                response.raise_for_status()
            except Exception as error:
                logger.error(
                    f"[SendMessageHTTPClient] GRPC stream endpoint failed - "
                    f"project: {project_uuid}, status_code: {response.status_code}"
                )
                raise exceptions.UnableToSendMessage(str(error)) from error
            return

        url = f"{self.__host}/mr/msg/send"

        payload = {"user": user, "project_uuid": project_uuid, "urns": urns, "text": text}
        headers = {"Authorization": f"Token {self.__access_token}", "Content-Type": "application/json"}

        payload = json.dumps(payload).encode("utf-8")

        response = requests.post(url, data=payload, headers=headers)
        logger.debug(f"SendMessage response - text_len: {len(response.text or '')}")
        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToSendMessage(str(error)) from error


class WhatsAppBroadcastHTTPClient(DirectMessage):
    broadcast_timeout = None

    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def fix_json_string(self, json_str):
        """
        Fix a JSON string with control characters and unescaped quotes
        """
        # First, escape the quotes inside the text content
        # Look for patterns like: Notebook 15" and escape the quote
        json_str = re.sub(r"(\w+)(\s*)(\")(\s*\w+)", r"\1\2\\\"\4", json_str)

        # Remove newlines and whitespace between JSON structural elements
        # This regex finds newlines and spaces between JSON structure parts
        json_str = re.sub(r'{\s*"', '{"', json_str)
        json_str = re.sub(r'",\s*"', '","', json_str)
        json_str = re.sub(r":\s*{", ":{", json_str)
        json_str = re.sub(r"}\s*}", "}}", json_str)

        # Preserve newlines in text content by converting them to \\n
        # This will handle the actual text content newlines
        json_str = re.sub(
            r'(text":\s*")([^"]*?)(")', lambda m: m.group(1) + m.group(2).replace("\n", "\\n") + m.group(3), json_str
        )

        return json_str

    def parse_json_strings(self, json_str):
        try:
            obj = json.loads(json_str)
            return obj
        except json.JSONDecodeError:
            try:
                json_str_escaped = json_str.replace("\n", "\\n")
                obj = json.loads(json_str_escaped)
                return obj
            except json.JSONDecodeError:
                try:
                    obj = ast.literal_eval(json_str)
                    return obj
                except Exception:
                    try:
                        json_str_escaped = json_str.replace("\n", "\\n")
                        obj = ast.literal_eval(json_str_escaped)
                        return obj
                    except Exception:
                        # if json is not valid ignore it
                        pass

    def get_json_strings(self, text):
        marked_text = re.sub(r'(?<=[}\]"])\s*{"msg":', r'SPLIT_HERE{"msg":', text)
        json_strings = marked_text.split("SPLIT_HERE")
        result = []
        for json_str in json_strings:
            _, json_str = self.get_json_strings_from_text(json_str)
            json_str = json_str.strip().strip("\n")
            json_str = self.fix_json_string(json_str)
            if json_str.startswith('{"msg":'):
                try:
                    json_dict = self.parse_json_strings(json_str)
                    if json_dict:
                        result.append(json_dict)
                except json.JSONDecodeError:
                    pass
        return result

    def send_direct_message(
        self,
        msg: str,
        urns: List,
        project_uuid: str,
        user: str,
        full_chunks: List[Dict] = None,
        backend: str = "BedrockBackend",
        **kwargs,
    ) -> None:
        if backend == "BedrockBackend":
            msgs = self.format_response_for_bedrock(msg, urns, project_uuid, user, full_chunks)
        else:
            msgs = self.format_message_for_openai(msg, urns, project_uuid, user, full_chunks)

        apply_ig_comment_fields_to_broadcast_msgs(msgs, ig_comment_fields_from_kwargs(kwargs))

        for msg in msgs:
            response = FlowsRESTClient().whatsapp_broadcast(
                urns,
                msg,
                project_uuid,
                timeout=self.broadcast_timeout,
            )
            try:
                response.raise_for_status()
            except Exception as error:
                raise exceptions.UnableToSendMessage(str(error)) from error

    def format_response_for_bedrock(
        self, msg: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]
    ) -> List[Dict]:
        msgs = self.get_json_strings(msg)
        if not msgs:
            msgs = [{"msg": {"text": str(msg)}}]
        return msgs

    def format_message_for_openai(
        self, msg: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]
    ) -> List[Dict]:
        msgs = None

        if isinstance(msg, str):
            try:
                msgs = json.loads(msg)
            except json.JSONDecodeError:
                # Plain text message, not JSON - this is expected behavior
                msgs = {"msg": {"text": msg}}
        else:
            msgs = msg

        if not isinstance(msgs, list):
            msgs = [msgs]

        return msgs

    def get_json_strings_from_text(self, text):
        pattern = r'(.*?)\s*(\{[\s\S]*"msg"[\s\S]*\})'

        match = re.search(pattern, text)
        if match:
            thought_text = match.group(1).strip()
            json_text = match.group(2)
            return thought_text, json_text

        return None, text

    def string_to_simple_text(self, text):
        return {"msg": {"text": text}}


class InstagramCommentBroadcastHTTPClient(WhatsAppBroadcastHTTPClient):
    """Send a plain-text Instagram comment reply through the broadcast API."""

    broadcast_timeout = 30

    @staticmethod
    def _single_text_message(msg: str, formatted_msgs: List[Dict]) -> List[Dict]:
        texts = []
        for item in formatted_msgs:
            item_msg = item.get("msg") if isinstance(item, dict) else None
            text = item_msg.get("text") if isinstance(item_msg, dict) else None
            if text is not None:
                texts.append(str(text))

        text = "\n\n".join(texts) if texts else str(msg)
        return [{"msg": {"text": text}}]

    def format_response_for_bedrock(
        self, msg: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]
    ) -> List[Dict]:
        formatted_msgs = super().format_response_for_bedrock(msg, urns, project_uuid, user, full_chunks)
        return self._single_text_message(msg, formatted_msgs)

    def format_message_for_openai(
        self, msg: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]
    ) -> List[Dict]:
        formatted_msgs = super().format_message_for_openai(msg, urns, project_uuid, user, full_chunks)
        return self._single_text_message(msg, formatted_msgs)
