from nexus.intelligences.llms.client import LLMClient
from router.reflection.wenigpt import WenigPTSharkReflection


MODEL_REFLECTION_VERSIONS = {
    "wenigpt_shark": WenigPTSharkReflection
}


def call_llm_reflection_model(
    llm_model: LLMClient,
    prompt_to_reflect: str,
    message_to_reflect: str,
    last_response: str,

    strategy=None
) -> str:
    reflection = MODEL_REFLECTION_VERSIONS.get(llm_model.code)(strategy=strategy)
    return reflection.reflect(
        message_to_reflect
    )
