from typing import NamedTuple


class InvokeAgentsResult(NamedTuple):
    """Return value from OpenAIBackend.invoke_agents when orchestration completes."""

    text: str
    skip_dispatch: bool
