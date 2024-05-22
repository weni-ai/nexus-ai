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

            sources.append({
                "filename": file_info.get("filename"),
                "uuid": file_uuid,
                "created_file_name": file_info.get("created_file_name"),
                "extension_file": file_info.get("extension_file"),
            })

        return {"type": "broadcast", "message": text, "fonts": sources}
