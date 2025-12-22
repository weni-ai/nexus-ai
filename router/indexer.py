from typing import List


def get_chunks(indexer, text: str, content_base_uuid: str) -> List[str]:
    client = indexer
    response = client.search_data(content_base_uuid=content_base_uuid, text=text)
    if response.get("status") == 200:
        texts_chunks: List[str] = response.get("data").get("response")
        return texts_chunks
    return []
