from typing import List, Dict, Callable, ClassVar

from router.direct_message import DirectMessage


class SimulateBroadcast(DirectMessage):
    def __init__(self, host: str, access_token: str, get_file_info: Callable) -> None:
        self.__host = host
        self.__access_token = access_token
        self.get_file_info = get_file_info

    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]) -> None:

        fonts = []
        for chunk in full_chunks:
            file_uuid = chunk.get("file_uuid")
            file_info = self.get_file_info(file_uuid)

            fonts.append({
                "filename": file_info.get("filename"),
                "uuid": file_uuid,
                "created_file_name": file_info.get("created_file_name"),
                "extension_file": file_info.get("extension_file"),
            })

        return {"type": "broadcast", "message": text, "fonts": fonts}
