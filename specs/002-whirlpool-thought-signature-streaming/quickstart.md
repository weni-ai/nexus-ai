# Quickstart: Verify Whirlpool Thought-Signature Streaming

## Local verification

From the `nexus-ai` repository:

```bash
~/.local/bin/poetry run pytest \
  inline_agents/backends/openai/custom_providers/tests/test_translate.py \
  inline_agents/backends/openai/custom_providers/tests/test_whirlpool_model.py \
  inline_agents/backends/openai/custom_providers/tests/test_registry.py
```

Expected coverage:

- A real `thoughtSignature` survives non-streamed and streamed SDK roundtrips.
- An unsigned historical/injected call receives the validation-skip sentinel.
- Parallel tool results share one user turn.
- Whirlpool resolves only for its vendor/custom prefix.
- OpenAI and LiteLLM model resolution remains unchanged.

## Diff verification

```bash
git diff --check
git diff --stat origin/main...
git diff origin/main... -- \
  inline_agents/backends/openai/custom_providers \
  specs/002-whirlpool-thought-signature-streaming
```

No database migration, public API, shared manager prompt, or non-Whirlpool adapter should appear.

## Production verification after deploy

1. Exercise a Whirlpool conversation that invokes a tool and continues with its result.
2. In Langfuse, verify the next `generateContent` payload has `thoughtSignature` beside `functionCall`; do not copy the signature or customer content into tickets.
3. Verify Sentry issue NEXUS-2WF receives no new event during the agreed observation window.
4. Exercise one normal OpenAI or Mantle project and confirm its model/request path is unchanged.

If instruction behavior still differs on the QA project, inspect only configuration metadata and compare the effective shared manager instruction source with `systemInstruction`. Do not print credentials, customer PII, full prompts, or token URLs.
