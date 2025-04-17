import ast
import json
import re

from typing import List, Dict, Callable

from router.direct_message import DirectMessage

class SimulateBroadcast(DirectMessage):
    def __init__(self, host: str, access_token: str, get_file_info: Callable) -> None:
        self.__host = host
        self.__access_token = access_token
        self.get_file_info = get_file_info

    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]) -> None:

        sources: List[Dict] = []
        seen_uuid: List[str] = []

        for chunk in full_chunks:
            file_uuid = chunk.get("file_uuid")

            if file_uuid in seen_uuid:
                continue

            seen_uuid.append(file_uuid)

            file_info = self.get_file_info(file_uuid)

            if file_info:
                sources.append({
                    "filename": file_info.get("filename"),
                    "uuid": file_uuid,
                    "created_file_name": file_info.get("created_file_name"),
                    "extension_file": file_info.get("extension_file"),
                })

        return {"type": "broadcast", "message": text, "fonts": sources}


class SimulateWhatsAppBroadcastHTTPClient(DirectMessage):

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
        json_str = re.sub(r'(text":\s*")([^"]*?)(")', 
                        lambda m: m.group(1) + m.group(2).replace('\n', '\\n') + m.group(3),
                        json_str)
        
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
                except Exception as e:
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
            thought_text, json_str = self.get_json_strings_from_text(json_str)
            if thought_text:
                result.append(self.string_to_simple_text(thought_text))
            json_str = json_str.strip().strip('\n')
            json_str = self.fix_json_string(json_str)
            if json_str.startswith('{"msg":'):
                try:
                    json_dict = self.parse_json_strings(json_str)
                    if json_dict:
                        result.append(json_dict)
                except json.JSONDecodeError as e:
                    pass
        return result

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

    def send_direct_message(
        self,
        msg: Dict,
        urns: List,
        project_uuid: str,
        user: str,
        full_chunks: List[Dict] = None
    ) -> None:
        msgs = self.get_json_strings(msg)

        return {"type": "broadcast", "message": msgs, "fonts": []}