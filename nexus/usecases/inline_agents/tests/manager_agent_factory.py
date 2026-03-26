import factory
import pendulum

from nexus.inline_agents.backends.openai.models import ManagerAgent


class ManagerAgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ManagerAgent

    name = factory.Sequence(lambda n: f"Manager {n}")
    base_prompt = "base prompt"
    foundation_model = "gpt-4o-mini"
    model_vendor = "openai"
    model_has_reasoning = False
    max_tokens = 2048
    collaborator_max_tokens = 2048
    reasoning_summary = "auto"
    parallel_tool_calls = False
    audio_orchestration_max_tokens = 2048
    audio_orchestration_collaborator_max_tokens = 2048
    component_tools_descriptions = {}
    formatter_agent_reasoning_summary = "auto"
    formatter_agent_send_only_assistant_message = False
    formatter_agent_tools_descriptions = {}
    formatter_agent_foundation_model = "gpt-4o-mini"
    formatter_agent_model_has_reasoning = False
    formatter_tools_descriptions = {}
    collaborators_foundation_model = "gpt-4o-mini"
    override_collaborators_foundation_model = False
    default = False
    public = True
    release_date = factory.LazyFunction(pendulum.now)
