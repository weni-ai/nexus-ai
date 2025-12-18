from django.conf import settings

# todo: make supervisor abstract class


class SupervisorRepository:
    @classmethod
    def get_foundation_model(
        cls,
        supervisor=None,
        foundation_model: str = None,
        default_supervisor_foundation_model: str = None,
    ) -> str:
        if foundation_model in settings.LOCKED_FOUNDATION_MODELS:
            return foundation_model

        # Cached data is always provided from start_inline_agents for OpenAI backend
        # Use cached value directly (may be None if not configured)
        custom_project_model = default_supervisor_foundation_model
        if custom_project_model:
            return custom_project_model

        supervisor_default_model = supervisor.foundation_model

        if foundation_model:
            supervisor_default_model = foundation_model

        return supervisor_default_model
