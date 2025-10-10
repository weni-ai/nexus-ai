from typing import List, Dict

import requests
import json
import re
import ast
from nexus.internals.flows import FlowsRESTClient
from router.direct_message import DirectMessage, exceptions
import sentry_sdk


class SendMessageHTTPClient(DirectMessage):

    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict], **kwargs) -> None:
        url = f"{self.__host}/mr/msg/send"

        payload = {"user": user, "project_uuid": project_uuid, "urns": urns, "text": text}
        headers = {
            "Authorization": f"Token {self.__access_token}",
            'Content-Type': 'application/json'
        }

        payload = json.dumps(payload).encode("utf-8")

        response = requests.post(url, data=payload, headers=headers)
        print("Resposta: ", response.text)
        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToSendMessage(str(error))


class WhatsAppBroadcastHTTPClient(DirectMessage):

    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def fix_json_string(self, json_str):
        """
        Fix a JSON string with control characters and unescaped quotes
        """
        # First, escape the quotes inside the text content
        # Look for patterns like: Notebook 15" and escape the quote
        json_str = re.sub(r'(\w+)(\s*)(\")(\s*\w+)', r'\1\2\\\"\4', json_str)

        # Remove newlines and whitespace between JSON structural elements
        # This regex finds newlines and spaces between JSON structure parts
        json_str = re.sub(r'{\s*"', '{"', json_str)
        json_str = re.sub(r'",\s*"', '","', json_str)
        json_str = re.sub(r':\s*{', ':{', json_str)
        json_str = re.sub(r'}\s*}', '}}', json_str)

        # Preserve newlines in text content by converting them to \\n
        # This will handle the actual text content newlines
        json_str = re.sub(
            r'(text":\s*")([^"]*?)(")',
            lambda m: m.group(1) + m.group(2).replace('\n', '\\n') + m.group(3),
            json_str
        )

        return json_str

    def parse_json_strings(self, json_str):
        try:
            obj = json.loads(json_str)
            return obj
        except json.JSONDecodeError:
            try:
                json_str_escaped = json_str.replace('\n', '\\n')
                obj = json.loads(json_str_escaped)
                return obj
            except json.JSONDecodeError:
                try:
                    # print(f"Error parsing JSON: {json_str}")
                    obj = ast.literal_eval(json_str)
                    return obj
                except Exception:
                    try:
                        json_str_escaped = json_str.replace('\n', '\\n')
                        obj = ast.literal_eval(json_str_escaped)
                        return obj
                    except Exception:
                        # if json is not valid ignore it
                        pass

    def get_json_strings(self, text):
        marked_text = re.sub(r'(?<=[}\]"])\s*{"msg":', r'SPLIT_HERE{"msg":', text)
        json_strings = marked_text.split('SPLIT_HERE')
        result = []
        for json_str in json_strings:
            _, json_str = self.get_json_strings_from_text(json_str)
            json_str = json_str.strip().strip('\n')
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
        msg: Dict,
        urns: List,
        project_uuid: str,
        user: str,
        full_chunks: List[Dict] = None,
        backend: str = "BedrockBackend",
        **kwargs
    ) -> None:

        print("!!!!!!!!!!!!!!PASSOU PELO SEND_DIRECT_MESSAGE!!!!!!!!!!!!!!!!")
        print("backend            ", backend)
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

        if backend == "BedrockBackend":
            msgs = self.format_response_for_bedrock(msg, urns, project_uuid, user, full_chunks)
        else:
            msgs = self.format_message_for_openai(msg, urns, project_uuid, user, full_chunks)

        for msg in msgs:
            response = FlowsRESTClient().whatsapp_broadcast(urns, msg, project_uuid)
            try:
                response.raise_for_status()
            except Exception as error:
                raise exceptions.UnableToSendMessage(str(error))

    def format_response_for_bedrock(self, msg: Dict, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]) -> None:
        msgs = self.get_json_strings(msg)
        if not msgs:
            msgs = [{"msg": {"text": str(msg)}}]
        return msgs

    def format_message_for_openai(self, msg: Dict, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]) -> Dict:
        try:
            msgs = json.loads(msg)
        except Exception as error:
            msgs = msg
            sentry_context = {
                "message": msg,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "project_uuid": project_uuid,
                "preview": False,
            }
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_context("session_error", sentry_context)
            sentry_sdk.capture_exception(error)

        print("!!!!!!!!!!!!!! PELO OPENAI!!!!!!!!!!!!!!!!")
        print(type(msgs))
        print(msgs)
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

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
        return {
            "msg": {
                "text": text
            }
        }
