from nexus.projects.models import BedrockGuardrailPool
from nexus.usecases.guardrails.bedrock_guardrail_pool import (
    BedrockGuardrailPoolService,
    ResolvedGuardrailPool,
)


def fake_pool_resolve(category_states, client=None):
    """Mock Bedrock pool resolve that persists a registry row without calling AWS."""
    blocked = BedrockGuardrailPoolService.blocked_slugs_from_states(category_states)
    if not blocked:
        return None
    key = BedrockGuardrailPoolService.combination_key(blocked)
    pool, created = BedrockGuardrailPool.objects.get_or_create(
        combination_key=key,
        defaults={
            "category_slugs": blocked,
            "bedrock_guardrail_identifier": f"gr-{key[:40]}",
            "bedrock_guardrail_version": "1",
        },
    )
    return ResolvedGuardrailPool(pool=pool, created=created)
