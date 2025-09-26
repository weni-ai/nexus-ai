from nexus import settings

from router.tasks.tasks import start_route, start_multi_agents
from .interfaces import InlineAgentTaskManager, TaskManagerBackend
from .redis_task_manager import RedisTaskManager
from .dynamo_task_manager import DynamoTaskManager


def get_task_manager() -> InlineAgentTaskManager:
    """
    Get the task manager instance based on configuration.
    Returns DynamoTaskManager if TASK_MANAGER_BACKEND is set to 'dynamo',
    otherwise returns RedisTaskManager.
    """
    backend_setting = getattr(
        settings, "TASK_MANAGER_BACKEND", TaskManagerBackend.REDIS.value
    )

    if isinstance(backend_setting, TaskManagerBackend):
        backend_value = backend_setting.value
    else:
        backend_value = backend_setting

    try:
        backend = TaskManagerBackend(backend_value)
    except ValueError:
        raise ValueError(
            f"Invalid task manager backend: {backend_value}. Valid options: {[b.value for b in TaskManagerBackend]}"
        )

    match backend:
        case TaskManagerBackend.DYNAMO:
            return DynamoTaskManager()
        case TaskManagerBackend.REDIS:
            return RedisTaskManager()
        case _:
            raise ValueError(f"Unhandled task manager backend: {backend.value}")


__all__ = [
    "InlineAgentTaskManager",
    "TaskManagerBackend",
    "RedisTaskManager",
    "DynamoTaskManager",
    "get_task_manager",
    "start_route",
    "start_multi_agents",
]
