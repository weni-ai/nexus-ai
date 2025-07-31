from typing import Dict, Any
from agents import function_tool
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase


@function_tool
def search_in_knowledge_base(content_base_uuid: str, text: str, number_of_results: int = 5) -> Dict[str, Any]:
    """
    Perform a similarity search in a vector database to retrieve data relevant to the input text.

    Args:
        content_base_uuid: The UUID of the content base to search in.
        text: The text to search for.
        number_of_results: The number of results to return.
    """
    bedrock_file_database = BedrockFileDatabase()

    return bedrock_file_database.search_data(content_base_uuid, text, number_of_results)
