# Quickstart: Rationale on the Live Answer Stream

**Date**: 2026-10-06  
**Contract**: [contracts/outgoing-message-kind.md](contracts/outgoing-message-kind.md)

## 1. Prerequisites

- Branch `003-rationale-message-kind`.
- A project with rationale enabled, components off, and the live stream enabled (`is_grpc_enabled` true: not components, and stream support on).
- The progressive-feedback instruction still tells the manager to send a short feedback message before a tool or agent call. It must not tell the model to hide that sentence in `reasoning.summary`.

## 2. Unit checks

From `nexus-ai`:

```bash
poetry run coverage run --source='.' manage.py test \
  inline_agents.backends.openai.grpc.tests \
  inline_agents.backends.openai.tests.test_rationale_stream \
  nexus.inline_agents.tests \
  --verbosity=2 --noinput
poetry run coverage report --fail-under=75
```

Adjust the test module paths to the files added by [tasks.md](tasks.md) if a name differs. Expected:

- A held sentence followed by a tool call becomes one `rationale` message and does not appear in any `delta`.
- Two tool calls produce `rationale_index` `"1"` then `"2"`.
- Text with no tool call is released only as `delta` messages plus one `completed`, both `final_response`.
- Rationale disabled produces no `rationale` message.
- A stored rationale row keeps its kind and index; a row with both columns null is serialized without those keys.

## 3. One streamed turn

Run a shopper message that makes the manager report progress and then call an agent. Capture the stream.

Expected order:

1. `setup`
2. One or more `type: rationale`, full text, `message_kind=rationale`, indexes `"1"`, `"2"`, …, stream still open
3. `type: delta` chunks whose concatenation is the answer and not the progress sentence, each with `message_kind=final_response`
4. `type: completed` with the full answer, `message_kind=final_response`, stream closed

No second HTTP post of the progress sentence.

## 4. Reload

Read the inline conversation for that contact. The progress row and the answer row are distinguishable. Older rows do not grow a kind.

## 5. Out of this check

- Agent Builder preview (it does not open this stream).
- A project with components on.
