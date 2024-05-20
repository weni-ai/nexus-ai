from typing import List, Dict, Callable, ClassVar

from router.direct_message import DirectMessage


class SimulateBroadcast(DirectMessage):
    def __init__(self, host: str, access_token: str, get_file_info: Callable) -> None:
        self.__host = host
        self.__access_token = access_token
        self.get_file_info = get_file_info

    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]) -> None:

        sources = []
        for chunk in full_chunks:
            file_uuid = chunk.get("file_uuid")
            file_info = self.get_file_info(file_uuid)
            info = {
                "filename": file_info.get("filename"),
                "uuid": file_uuid,
                "created_file_name": file_info.get("created_file_name"),
                "extension_file": file_info.get("extension_file"),
            }
            sources.append(f"{info}")

        unique_sources = list(str(sources))
        sources = [eval(font) for font in unique_sources]

        return {"type": "broadcast", "message": text, "fonts": sources}
