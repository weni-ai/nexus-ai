from nexus.usecases.projects.get_by_uuid import get_project_by_uuid


# Define __getattr__ for lazy imports to avoid circular dependencies
def __getattr__(name):
    if name == "ProjectsUseCase":
        from nexus.usecases.projects.projects_use_case import ProjectsUseCase

        return ProjectsUseCase
    if name == "ConversationsUsecase":
        from nexus.usecases.projects.conversations import ConversationsUsecase

        return ConversationsUsecase
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_project_by_uuid",
    "ProjectsUseCase",
    "ConversationsUsecase",
]
