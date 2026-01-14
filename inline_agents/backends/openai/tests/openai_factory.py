import factory

from nexus.inline_agents.backends.openai.models import OpenAISupervisor, SupervisorAgent


class OpenAISupervisorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OpenAISupervisor

    name = factory.Sequence(lambda n: f"OpenAI Supervisor {n}")
    instruction = factory.Faker("text", max_nb_chars=200)
    foundation_model = "gpt-4"
    prompt_override_configuration = factory.LazyFunction(lambda: {"temperature": 0.7})
    action_groups = factory.LazyFunction(lambda: [{"name": "default_action", "description": "Default action"}])
    knowledge_bases = factory.LazyFunction(lambda: [{"name": "default_kb", "description": "Default knowledge base"}])
    human_support_prompt = factory.Faker("text", max_nb_chars=200)
    human_support_action_groups = factory.LazyFunction(
        lambda: [{"name": "human_support", "description": "Human support action"}]
    )
    components_prompt = factory.Faker("text", max_nb_chars=200)
    components_human_support_prompt = factory.Faker("text", max_nb_chars=200)
    default_instructions_for_collaborators = factory.Faker("text", max_nb_chars=200)


class SupervisorAgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SupervisorAgent

    name = factory.Sequence(lambda n: f"Supervisor Agent {n}")
    default = True
    public = True
    created_on = factory.Faker("past_datetime")

    base_prompt = factory.Faker("text", max_nb_chars=500)
    foundation_model = "gpt-4o"
    model_vendor = "OpenAI"
    model_has_reasoning = False

    api_key = None
    api_base = None
    api_version = None

    max_tokens = 2048
    collaborator_max_tokens = 2048
    reasoning_effort = None
    reasoning_summary = "auto"

    tools = factory.LazyFunction(dict)
    knowledge_bases = factory.LazyFunction(list)

    human_support_prompt = factory.Faker("text", max_nb_chars=200)
    human_support_tools = factory.LazyFunction(dict)

    audio_orchestration_max_tokens = 2048
    audio_orchestration_collaborator_max_tokens = 2048

    header_components_prompt = factory.Faker("text", max_nb_chars=200)
    footer_components_prompt = factory.Faker("text", max_nb_chars=200)
    component_tools_descriptions = factory.LazyFunction(dict)

    formatter_agent_prompt = factory.Faker("text", max_nb_chars=300)
    formatter_agent_reasoning_effort = None
    formatter_agent_reasoning_summary = "auto"
    formatter_agent_send_only_assistant_message = False
    formatter_agent_tools_descriptions = factory.LazyFunction(dict)
    formatter_agent_foundation_model = "gpt-4o-mini"
    formatter_agent_model_has_reasoning = False
    formatter_tools_descriptions = factory.LazyFunction(dict)

    collaborators_foundation_model = "gpt-4o"
    override_collaborators_foundation_model = False
    default_instructions_for_collaborators = factory.Faker("text", max_nb_chars=200)
