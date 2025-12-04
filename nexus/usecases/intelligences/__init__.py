# This module exports use case classes and functions
# Import individual items as needed to avoid circular dependencies

# Cache for imported attributes to avoid repeated imports
_import_cache = {}


def _lazy_import(module_name, item_name):
    """Lazy import helper to avoid circular dependencies."""
    import importlib

    cache_key = (module_name, item_name)
    if cache_key in _import_cache:
        return _import_cache[cache_key]

    try:
        module = importlib.import_module(module_name)
        attr = getattr(module, item_name)
        _import_cache[cache_key] = attr
        return attr
    except (ImportError, AttributeError) as e:
        # Re-raise with more context for debugging
        raise AttributeError(f"Failed to lazy import {item_name!r} from {module_name!r}: {e}") from e


# Define __getattr__ for lazy imports
def __getattr__(name):
    if name in [
        # Create
        "CreateContentBaseFileUseCase",
        "CreateContentBaseLinkUseCase",
        "CreateContentBaseTextUseCase",
        "CreateContentBaseUseCase",
        "CreateIntelligencesUseCase",
        "create_integrated_intelligence",
        "create_llm",
        # Delete
        "DeleteContentBaseFileUseCase",
        "DeleteContentBaseLinkUseCase",
        "DeleteContentBaseTextUseCase",
        "DeleteContentBaseUseCase",
        "DeleteIntelligenceUseCase",
        # Get by UUID
        "get_by_content_base_file_uuid",
        "get_by_content_base_link_uuid",
        "get_by_contentbasetext_uuid",
        "get_by_contentbase_uuid",
        "get_by_intelligence_uuid",
        "get_default_content_base_by_project",
        "get_integrated_intelligence_by_project",
        "get_project_and_content_base_data",
        # DTOs
        "ContentBaseDTO",
        "ContentBaseFileDTO",
        "ContentBaseLinkDTO",
        "ContentBaseLogsDTO",
        "ContentBaseTextDTO",
        "LLMDTO",
        "UpdateContentBaseFileDTO",
        "UpdateLLMDTO",
        # List
        "ListAllIntelligenceContentUseCase",
        "ListContentBaseFileUseCase",
        "ListContentBaseLinkUseCase",
        "ListContentBaseTextUseCase",
        "ListContentBaseUseCase",
        "ListIntelligencesUseCase",
        "get_llm_config",
        # Retrieve
        "RetrieveContentBaseFileUseCase",
        "RetrieveContentBaseLinkUseCase",
        "RetrieveContentBaseTextUseCase",
        "RetrieveContentBaseUseCase",
        "RetrieveIntelligenceUseCase",
        # Search
        "IntelligenceGenerativeSearchUseCase",
        # Update
        "UpdateContentBaseFileUseCase",
        "UpdateContentBaseTextUseCase",
        "UpdateContentBaseUseCase",
        "UpdateIntelligenceUseCase",
        "UpdateLLMUseCase",
    ]:
        module_map = {
            # Create
            "CreateContentBaseFileUseCase": ("nexus.usecases.intelligences.create", "CreateContentBaseFileUseCase"),
            "CreateContentBaseLinkUseCase": ("nexus.usecases.intelligences.create", "CreateContentBaseLinkUseCase"),
            "CreateContentBaseTextUseCase": ("nexus.usecases.intelligences.create", "CreateContentBaseTextUseCase"),
            "CreateContentBaseUseCase": ("nexus.usecases.intelligences.create", "CreateContentBaseUseCase"),
            "CreateIntelligencesUseCase": ("nexus.usecases.intelligences.create", "CreateIntelligencesUseCase"),
            "create_integrated_intelligence": ("nexus.usecases.intelligences.create", "create_integrated_intelligence"),
            "create_llm": ("nexus.usecases.intelligences.create", "create_llm"),
            # Delete
            "DeleteContentBaseFileUseCase": ("nexus.usecases.intelligences.delete", "DeleteContentBaseFileUseCase"),
            "DeleteContentBaseLinkUseCase": ("nexus.usecases.intelligences.delete", "DeleteContentBaseLinkUseCase"),
            "DeleteContentBaseTextUseCase": ("nexus.usecases.intelligences.delete", "DeleteContentBaseTextUseCase"),
            "DeleteContentBaseUseCase": ("nexus.usecases.intelligences.delete", "DeleteContentBaseUseCase"),
            "DeleteIntelligenceUseCase": ("nexus.usecases.intelligences.delete", "DeleteIntelligenceUseCase"),
            # Get by UUID
            "get_by_content_base_file_uuid": (
                "nexus.usecases.intelligences.get_by_uuid",
                "get_by_content_base_file_uuid",
            ),
            "get_by_content_base_link_uuid": (
                "nexus.usecases.intelligences.get_by_uuid",
                "get_by_content_base_link_uuid",
            ),
            "get_by_contentbasetext_uuid": ("nexus.usecases.intelligences.get_by_uuid", "get_by_contentbasetext_uuid"),
            "get_by_contentbase_uuid": ("nexus.usecases.intelligences.get_by_uuid", "get_by_contentbase_uuid"),
            "get_by_intelligence_uuid": ("nexus.usecases.intelligences.get_by_uuid", "get_by_intelligence_uuid"),
            "get_default_content_base_by_project": (
                "nexus.usecases.intelligences.get_by_uuid",
                "get_default_content_base_by_project",
            ),
            "get_integrated_intelligence_by_project": (
                "nexus.usecases.intelligences.get_by_uuid",
                "get_integrated_intelligence_by_project",
            ),
            "get_project_and_content_base_data": (
                "nexus.usecases.intelligences.get_by_uuid",
                "get_project_and_content_base_data",
            ),
            # DTOs
            "ContentBaseDTO": ("nexus.usecases.intelligences.intelligences_dto", "ContentBaseDTO"),
            "ContentBaseFileDTO": ("nexus.usecases.intelligences.intelligences_dto", "ContentBaseFileDTO"),
            "ContentBaseLinkDTO": ("nexus.usecases.intelligences.intelligences_dto", "ContentBaseLinkDTO"),
            "ContentBaseLogsDTO": ("nexus.usecases.intelligences.intelligences_dto", "ContentBaseLogsDTO"),
            "ContentBaseTextDTO": ("nexus.usecases.intelligences.intelligences_dto", "ContentBaseTextDTO"),
            "LLMDTO": ("nexus.usecases.intelligences.intelligences_dto", "LLMDTO"),
            "UpdateContentBaseFileDTO": ("nexus.usecases.intelligences.intelligences_dto", "UpdateContentBaseFileDTO"),
            "UpdateLLMDTO": ("nexus.usecases.intelligences.intelligences_dto", "UpdateLLMDTO"),
            # List
            "ListAllIntelligenceContentUseCase": (
                "nexus.usecases.intelligences.list",
                "ListAllIntelligenceContentUseCase",
            ),
            "ListContentBaseFileUseCase": ("nexus.usecases.intelligences.list", "ListContentBaseFileUseCase"),
            "ListContentBaseLinkUseCase": ("nexus.usecases.intelligences.list", "ListContentBaseLinkUseCase"),
            "ListContentBaseTextUseCase": ("nexus.usecases.intelligences.list", "ListContentBaseTextUseCase"),
            "ListContentBaseUseCase": ("nexus.usecases.intelligences.list", "ListContentBaseUseCase"),
            "ListIntelligencesUseCase": ("nexus.usecases.intelligences.list", "ListIntelligencesUseCase"),
            "get_llm_config": ("nexus.usecases.intelligences.list", "get_llm_config"),
            # Retrieve
            "RetrieveContentBaseFileUseCase": (
                "nexus.usecases.intelligences.retrieve",
                "RetrieveContentBaseFileUseCase",
            ),
            "RetrieveContentBaseLinkUseCase": (
                "nexus.usecases.intelligences.retrieve",
                "RetrieveContentBaseLinkUseCase",
            ),
            "RetrieveContentBaseTextUseCase": (
                "nexus.usecases.intelligences.retrieve",
                "RetrieveContentBaseTextUseCase",
            ),
            "RetrieveContentBaseUseCase": ("nexus.usecases.intelligences.retrieve", "RetrieveContentBaseUseCase"),
            "RetrieveIntelligenceUseCase": ("nexus.usecases.intelligences.retrieve", "RetrieveIntelligenceUseCase"),
            # Search
            "IntelligenceGenerativeSearchUseCase": (
                "nexus.usecases.intelligences.search",
                "IntelligenceGenerativeSearchUseCase",
            ),
            # Update
            "UpdateContentBaseFileUseCase": ("nexus.usecases.intelligences.update", "UpdateContentBaseFileUseCase"),
            "UpdateContentBaseTextUseCase": ("nexus.usecases.intelligences.update", "UpdateContentBaseTextUseCase"),
            "UpdateContentBaseUseCase": ("nexus.usecases.intelligences.update", "UpdateContentBaseUseCase"),
            "UpdateIntelligenceUseCase": ("nexus.usecases.intelligences.update", "UpdateIntelligenceUseCase"),
            "UpdateLLMUseCase": ("nexus.usecases.intelligences.update", "UpdateLLMUseCase"),
        }
        module_name, attr_name = module_map[name]
        return _lazy_import(module_name, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Create
    "CreateContentBaseFileUseCase",
    "CreateContentBaseLinkUseCase",
    "CreateContentBaseTextUseCase",
    "CreateContentBaseUseCase",
    "CreateIntelligencesUseCase",
    "create_integrated_intelligence",
    "create_llm",
    # Delete
    "DeleteContentBaseFileUseCase",
    "DeleteContentBaseLinkUseCase",
    "DeleteContentBaseTextUseCase",
    "DeleteContentBaseUseCase",
    "DeleteIntelligenceUseCase",
    # Get by UUID
    "get_by_content_base_file_uuid",
    "get_by_content_base_link_uuid",
    "get_by_contentbasetext_uuid",
    "get_by_contentbase_uuid",
    "get_by_intelligence_uuid",
    "get_default_content_base_by_project",
    "get_integrated_intelligence_by_project",
    "get_project_and_content_base_data",
    # DTOs
    "ContentBaseDTO",
    "ContentBaseFileDTO",
    "ContentBaseLinkDTO",
    "ContentBaseLogsDTO",
    "ContentBaseTextDTO",
    "LLMDTO",
    "UpdateContentBaseFileDTO",
    "UpdateLLMDTO",
    # List
    "ListAllIntelligenceContentUseCase",
    "ListContentBaseFileUseCase",
    "ListContentBaseLinkUseCase",
    "ListContentBaseTextUseCase",
    "ListContentBaseUseCase",
    "ListIntelligencesUseCase",
    "get_llm_config",
    # Retrieve
    "RetrieveContentBaseFileUseCase",
    "RetrieveContentBaseLinkUseCase",
    "RetrieveContentBaseTextUseCase",
    "RetrieveContentBaseUseCase",
    "RetrieveIntelligenceUseCase",
    # Search
    "IntelligenceGenerativeSearchUseCase",
    # Update
    "UpdateContentBaseFileUseCase",
    "UpdateContentBaseTextUseCase",
    "UpdateContentBaseUseCase",
    "UpdateIntelligenceUseCase",
    "UpdateLLMUseCase",
]
