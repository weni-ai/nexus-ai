# Contract: Live Answer Stream Message Kind

**Consumer**: shopping assistant socket (Paulo Bernardo)
**Producer**: Nexus OpenAI live stream
**Date**: 2026-10-06
**Status**: Agreed in the 2026-10-06 exchange. If a field changes, Nexus tells the socket owner before they depend on it.

This contract replaces the earlier one, which posted rationale to `/mr/msg/send` and streamed the answer separately. That second connection is not part of this feature.

## Sequence

One bidirectional stream per turn. Every message shares `msg_id`, `channel_uuid`, `contact_urn`, `project_uuid`, and session metadata (`session_id`, `language`).

```text
setup
rationale          (zero or more, each complete, stream stays open)
delta              (answer tokens only)
completed          (full answer, stream closes)
```

## setup

Unchanged. `type` is `setup`, `content` is empty. No `message_kind`.

## rationale

Sent once per progress sentence, before any answer delta.

```json
{
  "type": "rationale",
  "msg_id": "<same id as the rest of the turn>",
  "content": "Vou consultar o status do pedido informado.",
  "metadata": {
    "session_id": "<session>",
    "language": "pt-BR",
    "message_kind": "rationale",
    "rationale_index": "1"
  }
}
```

- Does not close the stream.
- `rationale_index` is a string. The first update of the turn is `"1"`, the next is `"2"`. The next turn starts at `"1"` again.
- `content` is the full sentence, not a token fragment.
- The socket may ignore `type: rationale` until it is implemented. Answer delivery still completes.

## delta

Only final-answer tokens. The progress sentence is not a prefix and is not repeated here.

```json
{
  "type": "delta",
  "msg_id": "<same id>",
  "content": "Não foi ",
  "metadata": {
    "session_id": "<session>",
    "language": "pt-BR",
    "message_kind": "final_response"
  }
}
```

## completed

Unchanged except for the kind. Closes the stream. `content` is the full final answer.

```json
{
  "type": "completed",
  "msg_id": "<same id>",
  "content": "Não foi possível localizar o pedido.",
  "metadata": {
    "session_id": "<session>",
    "language": "pt-BR",
    "message_kind": "final_response"
  }
}
```

## When rationale is absent

Rationale disabled, no progress sentence, guardrail or canned refusal, or a turn that never opens this stream: no `rationale` message. Deltas and `completed` still declare `message_kind: final_response` when this stream is used.

## What this contract does not cover

- Preview.
- Components turns (they do not open this stream, and they cannot have rationale on at the same time).
- A second HTTP post of the same sentence.
- How the socket draws the loading state.
