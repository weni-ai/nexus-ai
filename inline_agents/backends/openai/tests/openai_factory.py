import factory

from nexus.inline_agents.backends.openai.models import OpenAISupervisor


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
